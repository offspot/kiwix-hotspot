hotspot-portal
====


## i18n

``` sh
# update message catalog
pybabel extract -F portal/babel.cfg -o portal/locale/messages.pot portal/
# add new locale (once per locale)
pybabel init -i portal/locale/messages.pot -d portal/locale -l fr
# update locales
pybabel update -i portal/locale/messages.pot -d portal/locale
# compile locales
pybabel compile -d portal/locale
```
