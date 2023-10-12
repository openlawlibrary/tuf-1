# Disclaimer

This is a fork of [Python-TUF](https://github.com/theupdateframework/python-tuf), maintained by the Open Law Library and
utilized by [The Archive Framework (TAF)](https://github.com/openlawlibrary/taf). The fork was created to make TUF's updater more
flexible, as TAF requires reading content of metadata and target files from bare Git repositories. Although these updates were
never merged upstream, this use case was taken into consideration during the rework of Python TUF's updater, and we encourage anyone
in need of the same flexibility to use the latest version of Python TUF. This fork will reach its end-of-life as soon as TAF's
codebase is updated, seeing that it currently relies on code that was removed from the newer versions of Python TUF.

For more information, please contact <info@openlawlib.org>
