Flask-Datadog
=============

This is a simple Flask extension that allows to access DogStatsd in your Flask application. It has an API
compatible with Flask-StatsD


Installation
------------

To install it, simply: ::

    pip install Flask-Datadog


Usage
-----

You only need to import and initialize your app ::

    from flask import Flask
    from flask_datadog import API, StatsD

    app = Flask(__name__)
    app.config['DATADOG_API_KEY']  = 'api_key'
    app.config['DATADOG_APP_KEY']  = 'app_key'
    statsd = StatsD(app)
    dogapi = API(app)
