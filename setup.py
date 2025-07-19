from setuptools import setup
import os

# Read version from version module
def get_version():
    version_file = os.path.join(os.path.dirname(__file__), 'configurator', '_version.py')
    with open(version_file, 'r') as f:
        for line in f:
            if line.startswith('__version__'):
                return line.split('=')[1].strip().strip('"\'')
    raise RuntimeError('Unable to find version string.')

# Read requirements from requirements.txt
with open(os.path.join(os.path.dirname(__file__), "requirements.txt")) as f:
    requirements = [line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")]

setup(
    name="configurator",
    version=get_version(),
    description="System configuration scripts",
    long_description="System configuration scripts",
    author="HiFiBerry",
    author_email="support@hifiberry.com",
    license="MIT",
    packages=["configurator"],
    install_requires=requirements,
    data_files=[
        ('/usr/lib/systemd/system', [
            'systemd/volume-store.service', 
            'systemd/volume-store.timer', 
            'systemd/sambamount.service', 
            'systemd/volume-restore.service',
            'systemd/config-server.service'
        ]),
        ('/usr/share/man/man1', [
            'man/config-asoundconf.1',
            'man/config-avahi.1',
            'man/config-cmdline.1',
            'man/config-configtxt.1',
            'man/config-db.1',
            'man/config-detect.1',
            'man/config-detectpi.1',
            'man/config-hattools.1',
            'man/config-network.1',
            'man/config-sambaclient.1',
            'man/config-sambamount.1',
            'man/config-soundcard.1',
            'man/config-volume.1',
            'man/config-wifi.1',
            'man/config-server.1'
        ]),
        ('/usr/share/man/man7', [
            'man/hifiberry-configurator.7',
        ]),
    ],
    entry_points={
        "console_scripts": [
            "config-asoundconf=configurator.asoundconf:main",
            "config-configtxt=configurator.configtxt:main",
            "config-hattools=configurator.hattools:main",
            "config-detect=configurator.soundcard_detector:main",
            "config-detectpi=configurator.pimodel:main",
            "config-soundcard=configurator.soundcard:main",
            "config-cmdline=configurator.cmdline:main",
            "config-sambaclient=configurator.sambaclient:main",
            "config-sambamount=configurator.sambamount:main",
            "config-wifi=configurator.wifi:main",
            "config-network=configurator.network:main",
            "config-db=configurator.configdb:main",
            "config-volume=configurator.volume:main",
            "config-avahi=configurator.avahi:main",
            "config-server=configurator.server:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)

