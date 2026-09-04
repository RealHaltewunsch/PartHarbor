from __future__ import annotations

import re

from setuptools import find_packages, setup

with open("README.md") as fh:
    long_description = fh.read()

# Read version from single source of truth
with open("partharbor/__init__.py") as fh:
    _match = re.search(r'^__version__ = "([^"]+)"', fh.read(), re.MULTILINE)
    if _match is None:
        raise RuntimeError("Cannot find __version__ in _version.py")
    _version = _match.group(1)

setup(
    name="partharbor",
    description=(
        "A graphical LCSC/JLCPCB search and EasyEDA-to-KiCad component importer"
    ),
    long_description=long_description,
    long_description_content_type="text/markdown",
    version=_version,
    author="PartHarbor contributors; converter by uPesy",
    url="https://github.com/RealHaltewunsch/PartHarbor",
    project_urls={
        "Code": "https://github.com/RealHaltewunsch/PartHarbor",
        "Upstream converter": "https://github.com/uPesy/easyeda2kicad.py",
    },
    license="AGPL-3.0",
    platforms="any",
    packages=find_packages(exclude=["tests", "utils"]),
    package_dir={"easyeda2kicad": "easyeda2kicad"},
    entry_points={
        "console_scripts": [
            "partharbor = partharbor.gui:main",
            "easyeda2kicad = easyeda2kicad.__main__:main",
        ]
    },
    python_requires=">=3.9",
    install_requires=[],
    extras_require={
        "dev": [
            "pre-commit>=3.0.0",
        ]
    },
    zip_safe=False,
    keywords="easyeda lcsc jlcpcb kicad library search conversion",
    classifiers=[
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Natural Language :: English",
        "Programming Language :: Python :: 3",
        "Topic :: Scientific/Engineering :: Electronic Design Automation (EDA)",
    ],
)
