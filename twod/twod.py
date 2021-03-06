#!/usr/bin/env python

"""twod TwoDNS host IP updater daemon.

twod is a client for the TwoDNS dynamic DNS service.

Copyright (C) 2014 Thomas Kager <tablet-mode AT monochromatic DOT cc>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see [http://www.gnu.org/licenses/].

"""

from __future__ import absolute_import

import logging.handlers
import logging.config

from argparse import ArgumentParser
from configparser import (SafeConfigParser, MissingSectionHeaderError,
                          NoSectionError, NoOptionError)
from json import dumps, loads
from lockfile.pidlockfile import PIDLockFile
from os import access, path, W_OK, X_OK
from random import randint
from re import match
from socket import inet_pton, error as socket_error, AF_INET, AF_INET6
from time import sleep

from daemon import DaemonContext
from requests import exceptions, Session

from twod._version import __version__


class _ServiceGenerator(object):
    """Select service URL depending on mode."""

    def __init__(self, services, mode):
        self.services = services
        self.mode = mode
        self.cur = -1

    def __iter__(self):
        return self

    def next(self):
        self.cur = self.cur + 1
        if self.mode == 'round_robin':
            if self.cur < len(self.services):
                service = self.services[self.cur]
            else:
                self.cur = 0
                service = self.services[self.cur]
            return service
        elif self.mode == 'random':
            self.cur = randint(0, (len(self.services) - 1))
            service = self.services[self.cur]
            return service


class _Data(object):
    """This is where the fun begins."""

    def __init__(self, conf):
        self.log = logging.getLogger('twod')
        self.ident = (conf['user'], conf['token'])
        self.url = conf['url']
        self.timeout = conf['timeout']
        self.redirects = conf['redirects']
        self.gen = _ServiceGenerator(conf['ip_url'].split(' '),
                                     conf['ip_mode'])
        self.rec_ip = self._get_rec_ip()

    def _validate_ip(self, ip, families=[4, 6]):
        """Validate textual IP address representation.

        Returns passed IP string if valid.
        Returns False on failure.

        """
        for family in families:
            try:
                if family == 4:
                    inet_pton(AF_INET, ip)
                elif family == 6:
                    inet_pton(AF_INET6, ip)
            except (socket_error, UnicodeEncodeError):
                # This is fine
                pass
            else:
                return ip
        return False

    def _get_service_url(self):
        """Get next URL from service generator."""
        return self.gen.next()

    def _get_ext_ip(self):
        """Get external IP.

        Returns external IP as string.
        Returns False on failure.

        """
        self.log.debug("Fetching external IP...")
        try:
            with Session() as s:
                s.max_redirects = self.redirects
                ip_request = s.get(self._get_service_url(), verify=True,
                                   timeout=self.timeout)
            ip_request.raise_for_status()
        except (exceptions.ConnectionError, exceptions.HTTPError) as e:
            self.log.warning("Error while fetching external IP: %s" % e)
            return False
        except exceptions.Timeout:
            self.log.warning("Failed to fetch external IP: Server did not "
                             "respond within %s seconds" % self.timeout)
            return False
        except exceptions.TooManyRedirects:
            self.log.warning("Failed to fetch external IP: "
                             "Too many redirects")
            return False
        except Exception as e:
            self.log.error("Unexpected error while fetching external IP "
                           ", retrying at next interval: %s" % e)
            return False
        else:
            ip = ip_request.text.rstrip()
            if not self._validate_ip(ip):
                self.log.warning("External IP discovery returned invalid IP")
            else:
                return ip

    def _get_rec_ip(self):
        """Get IP stored by TwoDNS.

        Returns IP as string. Returns False on failure.

        """
        self.log.debug("Fetching TwoDNS IP...")
        try:
            with Session() as s:
                s.max_redirects = self.redirects
                rec_request = s.get(
                    self.url, auth=self.ident, verify=True,
                    timeout=self.timeout)
            rec_request.raise_for_status()
        except (exceptions.ConnectionError, exceptions.HTTPError) as e:
            self.log.warning("Error while fetching IP from TwoDNS: %s" % e)
            return False
        except exceptions.Timeout:
            self.log.warning("Failed to fetch TwoDNS IP: Server did not "
                             "respond within %s seconds" % self.timeout)
            return False
        except exceptions.TooManyRedirects:
            self.log.warning("Failed to fetch TwoDNS IP: Too many redirects")
            return False
        except Exception as e:
            self.log.error("Unexpected error while fetching TwoDNS IP, "
                           "retrying at next interval: %s" % e)
            return False
        else:
            rec_json = loads(rec_request.text)
            ip = rec_json['ip_address']
            if not self._validate_ip(ip):
                self.log.warning("TwoDNS returned invalid IP")
            else:
                return ip

    def _check_ip(self):
        """Check if external IP matches recorded IP.

        Returns external IP as string if IPs differ. Returns False if the IPs
        match or an error occured.

        """
        self.log.debug("Checking if recorded IP matches current IP...")
        ext_ip = self._get_ext_ip()
        # something went wrong while fetching external IP but it's possible to
        # continue
        if not ext_ip:
            return False

        rec_ip = self.rec_ip
        if ext_ip == rec_ip:
            self.log.debug("IP has not changed.")
            return False
        else:
            return ext_ip

    def _update_ip(self, new_ip):
        """Update IP stored at TwoDNS."""
        self.log.debug("Updating recorded IP...")
        payload = {"ip_address": new_ip}
        try:
            with Session() as s:
                s.max_redirects = self.redirects
                rq = s.put(
                    self.url, auth=self.ident, data=dumps(payload),
                    verify=True, timeout=self.timeout)
            rq.raise_for_status()
        except (exceptions.ConnectionError, exceptions.HTTPError) as e:
            self.log.warning("Error while updating IP: %s" % e)
        except exceptions.Timeout:
            self.log.warning("Failed to update IP: Server did not respond "
                             "within %s seconds" % self.timeout)
        except exceptions.TooManyRedirects:
            self.log.warning("Failed to update IP: Too many redirects")
        except Exception as e:
            self.log.error("Unexpected error while updating TwoDNS IP, "
                           "retrying at next interval: %s" % e)
        else:
            self.log.info("IP changed to %s." % new_ip)
            self.rec_ip = new_ip


class Twod(object):
    """Twod class."""

    def __init__(self, config_path='/etc/twod/twodrc'):
        """Initialisation.

        * Setup logging
        * Read configuration
        * Initialise Data class

        """
        self._setup_logger()
        conf = self._read_config(config_path)
        self._setup_logger(conf['loglevel'])
        self.interval = conf['interval']
        self.conf = conf

    def _is_url(self, url):
        if not match(r'http(s)?://', url):
            raise ValueError(
                "Invalid URL: '%s' - has to start with 'http(s)'" % url)
        return url

    def _is_mode(self, mode):
        if mode not in ('random', 'round_robin'):
            raise ValueError("Invalid mode: '%s'" % mode)
        return mode

    def _setup_logger(self, level='WARNING'):
        """Setup logging."""
        logging.config.dictConfig({
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'daemon': {
                    'format': '%(asctime)s %(module)s[%(process)d]: '
                              '%(message)s'
                },
            },
            'handlers': {
                'syslog': {
                    'formatter': 'daemon',
                    'class': 'logging.handlers.SysLogHandler',
                    'address': '/dev/log',
                    'level': 'DEBUG',
                },
                'stderr': {
                    'formatter': 'daemon',
                    'class': 'logging.StreamHandler',
                    'stream': 'ext://sys.stderr',
                    'level': 'DEBUG',
                },
            },
            'loggers': {
                'twod': {
                    'handlers': ['syslog', 'stderr'],
                    'level': level,
                    'propagate': True
                }
            }
        })
        self.log = logging.getLogger('twod')

    def _read_config(self, config_path):
        """Read config.

        Exit on invalid config.

        """
        self.log.debug("Reading config...")
        conf = {}
        defaults = {
            'interval': '3600',
            'timeout': '16',
            'redirects': '2',
            'ip_mode': 'random',
            'loglevel': 'WARNING',
        }
        config = SafeConfigParser(defaults=defaults)
        try:
            # Check if config is even readable
            f = open(path.expanduser(config_path), 'r')

            # Read config
            config.readfp(f)
            f.close()

            conf['user'] = config.get('general', 'user')
            conf['token'] = config.get('general', 'token')
            conf['url'] = self._is_url(config.get('general', 'host_url'))
            conf['interval'] = config.getfloat('general', 'interval')
            conf['timeout'] = config.getfloat('general', 'timeout')
            conf['redirects'] = config.getint('general', 'redirects')
            conf['ip_mode'] = self._is_mode(config.get('ip_service', 'mode'))
            conf['ip_url'] = self._is_url(config.get('ip_service', 'ip_urls'))
            conf['loglevel'] = config.get('logging', 'level',
                                          fallback='WARNING')
        except (MissingSectionHeaderError, NoSectionError, NoOptionError,
                ValueError, IOError) as e:
            self.log.critical("Configuration error: %s" % e)
            exit(1)
        return conf

    def run(self):
        """Main loop."""
        data = _Data(self.conf)
        while(True):
            changed_ip = data._check_ip()
            if changed_ip:
                data._update_ip(changed_ip)
            sleep(self.interval)


def main():
    """Main function."""
    parser = ArgumentParser()
    parser.add_argument('-c', '--config', metavar='FILE',
                        help="load configuration from FILE")
    parser.add_argument('-p', '--pidfile', metavar='FILE',
                        help="use FILE as pidfile")
    parser.add_argument('-D', '--no-detach', dest='nodetach',
                        action='store_true',
                        help="do not detach from console")
    parser.add_argument('-V', '--version', action='version',
                        version='twod ' + __version__)
    args = parser.parse_args()

    if args.config and not path.isfile(path.expanduser(args.config)):
        parser.error("'%s' is not a file" % args.config)

    twod = Twod(args.config) if args.config else Twod()
    if args.nodetach:
        twod.run()
    else:
        pidfile = '/var/run/twod.pid'
        if args.pidfile:
            pidfile = args.pidfile
        twod.log.debug("Moving to background...")

        # Try to catch issues with pidfile before detaching, but as late as
        # possible to avoid race conditions
        if not access(path.dirname(pidfile), W_OK | X_OK):
            twod.log.critical("Unable to write pidfile")
            exit(1)
        with DaemonContext(pidfile=PIDLockFile(pidfile)):
            twod.run()


if __name__ == '__main__':
    main()
