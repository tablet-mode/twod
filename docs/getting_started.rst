.. _getting_started:

Getting started
===============

Configuration
-------------

``twod`` will look for a configuration file in ``/etc/twod/twodrc``. Optionally
you can tell ``twod`` to use a specified configuration file instead by using
the ``-c`` parameter.

Config format
^^^^^^^^^^^^^

.. code-block:: ini

   [general]
   user      = USERNAME
   token     = TOKEN
   host_url  = DNS_HOST_URL
   interval  = REFRESH_INTERVAL
   timeout   = HTTP_TIMEOUT
   redirects = MAX_HTTP_REDIRECTS

   [ip_service]
   mode      = MODE
   ip_urls   = URLS

   [logging]
   level     = LOGLEVEL

general section
"""""""""""""""

``user``
   Username used to authenticate to TwoDNS.

``token``
   Token used to authenticate to TwoDNS.

``host_url``
   URL of your TwoDNS host.

``interval``
   Refresh interval in seconds.

``timeout``
   Timeout for retrieving and setting your external IP, in seconds.

``redirects``
   Maximum number of redirects to follow on HTTP requests.

ip_service section
""""""""""""""""""

``mode``
   Controls after which pattern  the ``ip_service`` URL will be selected.
   Possible values:

      * ``random``: Chooses random ip service on every refresh.

      * ``round_robin``: Loop through ip services in the order they are
           defined.

``ip_urls``
   Space-separated list of URLs to fetch your external IP address from. **The IP
   has to be returned as plaintext without any HTML or other extra data.**

logging section
"""""""""""""""

``level``
   Log level. Can be one of:

      * `DEBUG`

      * `INFO`

      * `WARNING`

      * `ERROR`

      * `CRITICAL`

Example config
^^^^^^^^^^^^^^

.. literalinclude:: examples/twodrc.example
   :language: ini
