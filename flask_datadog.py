import logging
import time

from datadog import initialize
from datadog import api as dogapi
from datadog.dogstatsd.base import DogStatsd
from datadog.dogstatsd.context import TimedContextManagerDecorator
from flask import (
    g,
    request,
)


LOG = logging.getLogger(__name__)


class _TimedContextManagerDecorator(TimedContextManagerDecorator):

    def _send(self, start):
        elapsed = time.monotonic() - start
        use_ms = self.use_ms if self.use_ms is not None else True
        elapsed = int(round(1000 * elapsed)) if use_ms else elapsed

        if self.statsd:
            self.statsd.timing(self.metric, elapsed, self.tags, self.sample_rate)
        else:
            LOG.debug('TimedContextManagerDecorator: %s took %dms', self.metric, elapsed)

        self.elapsed = elapsed


class TimerWrapper(_TimedContextManagerDecorator):
    def __init__(self, statsd, *args, **kwargs):
        super(TimerWrapper, self).__init__(statsd, *args, **kwargs)

    def start(self):
        self.__enter__()

    def stop(self):
        self.__exit__(None, None, None)


class StatsD(object):
    def __init__(self, app=None, config=None):
        """
        Constructor for `flask_datadog.StatsD`

        >>> from flask_datadog import StatsD
        >>> app = Flask(__name__)
        >>> statsd = StatsD(app=app)

        :param app: Flask app to configure this client for, if `app` is `None`, then do not
            configure yet (call `init_app` manually instead)
        :type app: flask.Flask or None

        :param config: Configuration for this client to use instead of `app.config`
        :type config: dict or None
        """
        self.config = config
        self.statsd = None
        self.is_enabled = False

        # If an app was provided, then call `init_app` for them
        if app is not None:
            self.init_app(app)
        else:
            self.app = None

    def init_app(self, app, config=None):
        """
        Initialize Datadog DogStatsd client from Flask app

        >>> from flask_datadog import StatsD
        >>> app = Flask(__name__)
        >>> statsd = StatsD()
        >>> statsd.init_app(app=app)

        Available DogStatsd config settings:

          STATSD_HOST - statsd host to send metrics to (default: 'localhost')
          STATSD_MAX_BUFFER_SIZE - max number of metrics to buffer before sending, only used when batching (default: 50)
          STATSD_NAMESPACE - metric name prefix to use, e.g. 'app_name' (default: None)
          STATSD_PORT - statsd port to send metrics to (default: 8125)
          STATSD_TAGS - list of tags to include by default, e.g. ['env:prod'] (default: None)
          STATSD_USEMS - whether or not to report timing in milliseconds (default: False)

        Available Flask-Datadog config settings:

          DATADOG_CONFIGURE_MIDDLEWARE - whether or not to setup response timing middleware (default: True)
          DATADOG_RESPONSE_METRIC_NAME - the name of the response time metric (default: 'flask.response.time')
          DATADOG_RESPONSE_SIZE_METRIC_NAME - the name of the response time metric (default: 'flask.response.size')
          DATADOG_RESPONSE_SAMPLE_RATE - the sample rate to use for response timing middleware (default: 1)
          DATADOG_RESPONSE_AUTO_TAG - whether to auto-add request/response tags to response metrics (default: True)
          DATADOG_RESPONSE_ENDPOINT_TAG_NAME - tag name to use for request endpoint tag name (default: 'endpoint')
          DATADOG_RESPONSE_METHOD_TAG_NAME - tag name to use for the request method tag name (default: 'method')

        :param app: Flask app to configure this client for
        :type app: flask.Flask

        :param config: optional, dictionary of config values (defaults to `app.config`)
        :type config: dict
        """
        # Used passed in config if provided, otherwise use the config from `app`
        if config is not None:
            self.config = config
        elif self.config is None:
            self.config = app.config

        # Set default values for expected config properties
        self.config.setdefault('STATSD_HOST', 'localhost')
        self.config.setdefault('STATSD_MAX_BUFFER_SIZE', 50)
        self.config.setdefault('STATSD_NAMESPACE', None)
        self.config.setdefault('STATSD_PORT', 8125)
        self.config.setdefault('STATSD_TAGS', None)
        self.config.setdefault('STATSD_USEMS', False)
        self.config.setdefault('STATSD_SOCKET_PATH', None)

        self.app = app
        self.app.extensions['statsd'] = self

        # Configure DogStatsd client
        # https://github.com/DataDog/datadogpy/blob/v0.20.0/datadog/dogstatsd/base.py
        self.statsd = DogStatsd(host=self.config['STATSD_HOST'],
                                port=self.config['STATSD_PORT'],
                                max_buffer_size=self.config['STATSD_MAX_BUFFER_SIZE'],
                                namespace=self.config['STATSD_NAMESPACE'],
                                constant_tags=self.config['STATSD_TAGS'],
                                use_ms=self.config['STATSD_USEMS'],
                                socket_path=self.config['STATSD_SOCKET_PATH'])

        # Configure any of our middleware
        self.setup_middleware()
        self.is_enabled = True

    def _setdefault_tags(self, kwargs):
        tags = kwargs.get('tags')
        if tags is None:
            kwargs['tags'] = self.get_request_tags()

        return kwargs

    def timer(self, *args, **kwargs):
        """Helper to get a `flask_datadog.TimerWrapper` for this `DogStatsd` client"""
        if self.is_enabled:
            self._setdefault_tags(kwargs)

        return TimerWrapper(self.statsd, *args, **kwargs)

    def incr(self, *args, **kwargs):
        """Helper to expose `self.statsd.increment` under a shorter name"""
        if self.is_enabled:
            self._setdefault_tags(kwargs)
            return self.statsd.increment(*args, **kwargs)

    def decr(self, *args, **kwargs):
        """Helper to expose `self.statsd.decrement` under a shorter name"""
        if self.is_enabled:
            self._setdefault_tags(kwargs)
            return self.statsd.decrement(*args, **kwargs)

    def gauge(self, *args, **kwargs):
        """Helper to expose `self.statsd.gauge` with auto tagging"""
        if self.is_enabled:
            self._setdefault_tags(kwargs)
            return self.statsd.gauge(*args, **kwargs)

    def setup_middleware(self):
        """Helper to configure/setup any Flask-Datadog middleware"""
        # Configure response time middleware (if desired)
        self.config.setdefault('DATADOG_CONFIGURE_MIDDLEWARE', True)
        self.config.setdefault('DATADOG_RESPONSE_SIZE_METRIC_NAME', 'flask.response.size')
        self.config.setdefault('DATADOG_RESPONSE_METRIC_NAME', 'flask.response.time')
        self.config.setdefault('DATADOG_RESPONSE_SAMPLE_RATE', 1)
        self.config.setdefault('DATADOG_RESPONSE_AUTO_TAG', True)
        self.config.setdefault('DATADOG_RESPONSE_ENDPOINT_TAG_NAME', 'endpoint')
        self.config.setdefault('DATADOG_RESPONSE_METHOD_TAG_NAME', 'method')

        if self.config['DATADOG_CONFIGURE_MIDDLEWARE']:
            self.app.before_request(self.before_request)
            self.app.after_request(self.after_request)

    def before_request(self):
        """
        Flask-Datadog middleware handle for before each request
        """
        # Set the request start time
        g.request_start_time = time.monotonic()
        g.request_tags = []

        # Add some default request tags
        if self.config['DATADOG_RESPONSE_AUTO_TAG']:
            self.add_request_tags([
                # Endpoint tag
                '{tag_name}:{endpoint}'.format(tag_name=self.config['DATADOG_RESPONSE_ENDPOINT_TAG_NAME'],
                                               endpoint=str(request.endpoint).lower()),
                # Method tag
                '{tag_name}:{method}'.format(tag_name=self.config['DATADOG_RESPONSE_METHOD_TAG_NAME'],
                                             method=request.method.lower()),
            ])

    def after_request(self, response):
        """
        Flask-Datadog middleware handler for after each request

        :param response: the response to be sent to the client
        :type response: ``flask.Response``
        :rtype: ``flask.Response``
        """
        # Return early if we don't have the start time
        if not hasattr(g, 'request_start_time'):
            return response

        # start time might have been already computed by core middleware
        elapsed = g.get('request_elapsed_time')
        if not elapsed:
            # Get the response time for this request
            elapsed = time.time() - g.request_start_time

        # Convert the elapsed time to milliseconds if they want them
        if self.use_ms:
            elapsed = int(round(1000 * elapsed))

        # Add some additional response tags
        if self.config['DATADOG_RESPONSE_AUTO_TAG']:
            self.add_request_tags(['status_code:%d' % response.status_code])

        tags = self.get_request_tags()
        sample_rate = self.config['DATADOG_RESPONSE_SAMPLE_RATE']

        # Emit timing metric
        self.statsd.timing(self.config['DATADOG_RESPONSE_METRIC_NAME'],
                           elapsed,
                           tags,
                           sample_rate)

        # Emit response size metric
        if 'content-length' in response.headers:
            size = int(response.headers['content-length'])
            self.statsd.histogram(self.config['DATADOG_RESPONSE_SIZE_METRIC_NAME'],
                                  size,
                                  tags,
                                  sample_rate)

        # We ALWAYS have to return the original response
        return response

    def get_request_tags(self):
        """
        Get the current list of tags set for this request

        :rtype: list
        """
        try:
            return g.get('request_tags', [])
        except RuntimeError:
            return []

    def add_request_tags(self, tags):
        """
        Add the provided list of tags to the tags stored for this request

        :param tags: tags to add to this requests tags
        :type tags: list
        :rtype: list
        """
        # Get the current list of tags to append to
        # DEV: We use this method since ``self.get_request_tags`` will ensure that we get a list back
        current_tags = self.get_request_tags()

        # Append our new tags, and return the new full list of tags for this request
        try:
            g.request_tags = current_tags + tags
        except RuntimeError:
            return []

        return g.request_tags

    def __getattr__(self, name):
        """
        Magic method for fetching any underlying attributes from `self.statsd`

        We utilize `__getattr__` to ensure that we are always compatible with
        the `DogStatsd` client.
        """
        # If `self.statsd` has the attribute then return that attribute
        if self.statsd and hasattr(self.statsd, name):
            return getattr(self.statsd, name)

        raise AttributeError("'StatsD' has has attribute '{name}'".format(name=name))

    def __enter__(self):
        """
        Helper to expose the underlying `DogStatsd` client for context managing

        >>> statsd = StatsD(app=app)
        >>> # Batch any metrics within the `with` block
        >>> with statsd:
        >>>   statsd.increment('metric')
        """
        return self.statsd.__enter__()

    def __exit__(self, *args, **kwargs):
        """Helper to expose the underlying `DogStatsd` client for context managing"""
        return self.statsd.__exit__(*args, **kwargs)


class API(object):
    def __init__(self, app=None, config=None):
        """
        Constructor for `flask_datadog.API`

        >>> from flask_datadog import API
        >>> app = Flask(__name__)
        >>> dogapi = API(app=app)

        :param app: Flask app to configure this client for, if `app` is `None`, then do not
            configure yet (call `init_app` manually instead)
        :type app: flask.Flask or None

        :param config: Configuration for this client to use instead of `app.config`
        :type config: dict or None
        """
        self.config = config

        # If an app was provided, then call `init_app` for them
        if app is not None:
            self.init_app(app)
        else:
            self.app = None

    def init_app(self, app, config=None):
        """
        Initialize Datadog API client from Flask app

        >>> from flask_datadog import API
        >>> app = Flask(__name__)
        >>> dogapi = API()
        >>> dogapi.init_app(app=app)

        Available config settings:

          DATADOG_API_KEY - Datadog API key from https://app.datadoghq.com/account/settings#api
          DATADOG_APP_KEY - Datadog APP key from https://app.datadoghq.com/account/settings#api

        :param app: Flask app to configure this client for
        :type app: flask.Flask

        :param config: optional, dictionary of config values (defaults to `app.config`)
        :type config: dict
        """
        # Used passed in config if provided, otherwise use the config from `app`
        if config is not None:
            self.config = config
        elif self.config is None:
            self.config = app.config

        # Set default values for expected config properties
        self.config.setdefault('DATADOG_API_KEY', None)
        self.config.setdefault('DATADOG_APP_KEY', None)

        self.app = app

        # Initialize datadog client
        # DEV: Datadog client uses module level variables for storing API keys rather than initializing a
        #   class to manage a connection/and keys
        # https://github.com/DataDog/datadogpy/blob/v0.11.0/datadog/__init__.py
        # https://github.com/DataDog/datadogpy/blob/v0.11.0/datadog/api/__init__.py#L4-L9
        options = {
            'api_key': self.config['DATADOG_API_KEY'],
            'app_key': self.config['DATADOG_APP_KEY'],
        }
        initialize(**options)

    def __getattr__(self, name):
        """
        Magic method for fetching attributes from `datadog.api`

        We utilize `__getattr__` to ensure that we are always compatible with
        the `datadog.api` module.
        """
        # If `self.statsd` has the attribute then return that attribute
        if dogapi and hasattr(dogapi, name):
            return getattr(dogapi, name)

        raise AttributeError("'API' has no attribute '{name}'".format(name=name))
