#!/usr/bin/env python2

"""twod

twod is a client for the twodns.de dynamic dns service.

Copyright (C) 2013 Tablet Mode <tablet-mode AT monochromatic DOT cc>

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

from ConfigParser import SafeConfigParser, NoSectionError, NoOptionError
from json import dumps, loads
import lockfile
import logging.handlers
import logging.config
from optparse import OptionParser
from os import path
from random import randint 
from re import match
from time import sleep

from daemon import DaemonContext
from requests import get, put, exceptions


class _ServiceGenerator:
    """Select service URL depending on mode."""

    def __init__(self, services):
        self.services = services
        self.cur = 0

    def __iter__(self):
        return self

    def next(self, mode):
        if mode == 'round_robin':
            if self.cur < len(self.services):
                service = self.services[self.cur]
                self.cur = self.cur + 1
                return service
            else:
                self.cur = 0
                service = self.services[self.cur]
                return service
        elif mode == 'random':
            self.cur = randint(0, (len(self.services) - 1))
            service = self.services[self.cur]
            return service


class _Data:
    """Do pretty much everything."""

    def __init__(self, conf):
        self.log = logging.getLogger('twod')
        self.ident = (conf['user'], conf['password'])
        self.url = conf['url']
        self.ip_mode = conf['ip_mode']
        ip_url = conf['ip_url'].split(' ')
        self.gen = _ServiceGenerator(ip_url)
        self.rec_ip = self._get_rec_ip()

    def _get_service_url(self):
        return self.gen.next(self.ip_mode)

    def _get_ext_ip(self):
        """Get external IP.
        Returns external IP as string.
        Returns False on failure.

        """
        self.log.debug("Fetching external ip...")
        try:
            ip_request = get(self._get_service_url(), verify=True, timeout=16)
            ip_request.raise_for_status()
        except exceptions.ConnectionError as e:
            message = "Connection error while fetching external IP: %s" % e
            self.log.warning(message)
            return False
        except exceptions.HTTPError as e:
            message = "HTTP error while fetching external IP: %s" % e
            self.log.warning(message)
            return False
        except Exception as e:
            message = "Unexpected error while fetching external IP: %s" % e
            self.log.error(message)
            return False
        else:
            ip = ip_request.text.rstrip()
            return ip

    def _get_rec_ip(self):
        """Get IP stored by twodns.
        Returns IP as string. Returns False on failure.

        """
        self.log.debug("Fetching twodns ip...")
        try:
            rec_request = get(
                self.url, auth=self.ident, verify=True, timeout=16)
            rec_request.raise_for_status()
        except exceptions.ConnectionError as e:
            message = "Connection error while fetching IP from twodns: %s" % e
            self.log.warning(message)
            return False
        except exceptions.HTTPError as e:
            message = "HTTP error while fetching IP from twodns: %s" % e
            self.log.warning(message)
            return False
        except Exception as e:
            message = "Unexpected error while fetching IP from twodns: %s" % e
            self.log.error(message)
            return False
        else:
            rec_json = loads(rec_request.text)
            ip = rec_json['ip_address']
            return ip

    def _check_ip(self):
        """Check if external IP matches recorded IP.
        Returns external IP as string if IPs differ. Returns False if the IPs
        match or an error occured.

        """
        self.log.debug("Checking if recorded IP matches current IP...")
        ext_ip = self._get_ext_ip()
        if not ext_ip:
            return False
        rec_ip = self.rec_ip
        if ext_ip == rec_ip:
            self.log.debug("IP has not changed.")
            return False
        else:
            return ext_ip

    def _update_ip(self, new_ip):
        """Update IP stored at twodns."""
        self.log.debug("Updating recorded IP...")
        try:
            payload = {"ip_address": new_ip}
            r = put(
                self.url, auth=self.ident, data=dumps(payload), verify=True,
                timeout=16)
        except exceptions.ConnectionError as e:
            message = "Connection error while updating IP: %s" % e
            self.log.warning(message)
            return False
        except exceptions.HTTPError as e:
            message = "HTTP error while updating IP: %s" % e
            self.log.warning(message)
            return False
        except Exception as e:
            message = "Unexpected error while updating IP: %s" % e
            self.log.error(message)
            return False
        else:
            if(r.status_code == 200):
                message = "IP changed to %s." % new_ip
                self.log.info(message)
                self.rec_ip = new_ip
            else:
                message = "Failed to update IP."
                self.log.warning(message)
                return r.status_code


class Twod:
    """Twod class."""

    def __init__(self, config):
        self._setup_logger()
        conf = self._read_config(config)
        self._setup_logger(conf['loglevel'])
        self.interval = conf['interval']
        self.data = _Data(conf)

    def _is_url(self, url):
        if not match(r'http(s)?://', url):
            raise ValueError("Invalid URL: '%s'" % url)
        return url

    def _is_mode(self, mode):
        if not match(r'(random)|(round_robin)', mode):
            raise ValueError("Invalid mode: '%s'" % mode)
        return mode

    def _setup_logger(self, level='WARN'):
        """Setup logging."""

        logging.config.dictConfig({
            'version': 1,
            'disable_existing_loggers': False,
            'formatters': {
                'daemon': {
                    'format': '%(asctime)s %(module)s[%(process)d]: %(message)s'
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
                    'stream': 'ext://sys.stdout',
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

    def _read_config(self, custom):
        """Read config.
        Exit on invalid config.

        """

        self.log.debug("Reading config...")
        conf = {}
        config = SafeConfigParser()
        if custom:
            config.read([path.expanduser(custom)])
        else:
            config.read([
                '/etc/twod/twodrc',
                path.expanduser('~/.config/twod/twodrc'),
            ])
        try:
            conf['user'] = config.get('general', 'user')
            conf['password'] = config.get('general', 'password')
            conf['url'] = self._is_url(config.get('general', 'url'))
            conf['interval'] = config.getint('general', 'interval')
            conf['ip_mode'] = self._is_mode(config.get('ip_service', 'mode'))
            conf['ip_url'] = self._is_url(config.get('ip_service', 'urls'))
            conf['loglevel'] = config.get('logging', 'level')
        except NoSectionError as e:
            message = "Configuration error: %s" % e
            self.log.critical(message)
            exit(1)
        except NoOptionError as e:
            message = "Configuration error: %s" % e
            self.log.critical(message)
            exit(1)
        except ValueError as e:
            message = "Configuration error: %s" % e
            self.log.critical(message)
            exit(1)
        except Exception as e:
            message = "Unexpected error while reading config: %s" % e
            self.log.critical(message)
            exit(1)
        return conf

    def run(self):
        """Main loop."""
        data = self.data
        while(True):
            changed_ip = data._check_ip()
            if changed_ip:
                data._update_ip(changed_ip)
            sleep(self.interval)


def main():
    parser = OptionParser()
    parser.add_option('-c', '--config', dest='config',
                      help="load configuration from FILE", metavar='FILE')
    (options, args) = parser.parse_args()
    config = options.config

    if config and not path.isfile(path.expanduser(config)):
        parser.error("'%s' is not a file" % config)
        exit(1)

    twod = Twod(config)
    twod.run()


if __name__ == '__main__':
    with DaemonContext():
        main()
