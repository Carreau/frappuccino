# Configuration file for the Sphinx documentation builder.
#
# -- Project information -----------------------------------------------------

project = "frappuccino"
copyright = "2020, Matthias Bussonnier"
author = "Matthias Bussonnier"


# -- General configuration ---------------------------------------------------

extensions = []

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]
master_doc = "index"

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

import os

ON_RTD = os.environ.get("READTHEDOCS", None) == "True"
if not ON_RTD:
    import sphinx_rtd_theme

    html_theme = "sphinx_rtd_theme"
    html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
html_logo = "frappuccino.png"
