from setuptools import setup
import os

# Read requirements from requirements.txt
with open(os.path.join(os.path.dirname(__file__), "requirements.txt")) as f:
    requirements = [line.strip() for line in f.readlines() if line.strip() and not line.startswith("#")]

setup(
    name="configurator",
    version="1.6.3",
    description="System configuration scripts",
    long_description="System configuration scripts",
    author="HiFiBerry",
    author_email="support@hifiberry.com",
    license="MIT",
    packages=["configurator"],
    install_requires=requirements,
    data_files=[
        ('/usr/lib/systemd/system', ['systemd/volume-store.service', 'systemd/volume-store.timer']),
    ],
    entry_points={
        "console_scripts": [
            "config-asoundconf=configurator.asoundconf:main",
            "config-configtxt=configurator.configtxt:main",
            "config-hattools=configurator.hattools:main",
            "config-installer=configurator.installer:main",
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
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)

