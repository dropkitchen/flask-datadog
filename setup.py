from setuptools import setup

setup(
    name='Flask-Datadog',
    version='0.1.4',
    url='https://github.com/50onRed/flask-datadog.git',
    license='BSD',
    author='50onRed',
    author_email='marcus.mccurdy@gmail.com',
    description='Access to dogstatsd in your app.',
    py_modules=['flask_datadog'],
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=['Flask', 'datadog>=0.22'],
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
