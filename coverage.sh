#!/bin/bash
red='\033[1;31m'
info='\033[1;38;2;33;150;243m'
nm='\033[0m'

exit=0

echo -e "$info\0Checking for executables and vars...$nm\n"

which coverage &>/dev/null
if [[ $? -ne 0 ]]; then
  echo -e "$red\0Coverage not found$nm"
  exit=1
fi

which codecov &>/dev/null
if [[ $? -ne 0 ]]; then
  echo -e "$red\0Codecov not found$nm"
  exit=1
fi

if [[ -z ${VK_LOGIN+yup} ]]; then
  echo -e "$red\0VK_LOGIN not set$nm"
  exit=1
else
  echo -e "$info\0VK_LOGIN = ${VK_LOGIN}"
fi
if [[ -z ${VK_PASSWORD+yup} ]]; then
  echo -e "$red\0VK_PASSWORD not set$nm"
  exit=1
else
  echo -e "$info\0VK_PASSWORD = ${VK_PASSWORD}"
fi
if [[ -z ${CODECOV_TOKEN+yup} ]]; then
  echo -e "$red\0CODECOV_TOKEN not set$nm"
  exit=1
else
  echo -e "$info\0CODECOV_TOKEN = ${CODECOV_TOKEN}$nm"
fi
if [[ -z ${CODACY_PROJECT_TOKEN+yup} ]]; then
  echo -e "$red\0CODACY_PROJECT_TOKEN not set$nm"
  exit=1
else
  echo -e "$info\0CODACY_PROJECT_TOKEN = ${CODACY_PROJECT_TOKEN}$nm\n"
fi

if [[ exit -eq 1 ]]; then
  exit 1
fi

coverage run dump.py --help &>/dev/null
if [[ $? -ne 0 ]]; then echo -e "$red\0Failed to run --help$nm"; exit 1; fi

coverage run -a dump.py
if [[ $? -ne 0 ]]; then echo -e "$red\0Failed to run CUI$nm"; exit 1; fi

DUMP_ARGS="audio docs messages photo video attachments_only fave_photo fave_posts fave_video"
coverage run -a dump.py -l $VK_LOGIN -p $VK_PASSWORD --dump $DUMP_ARGS
if [[ $? -ne 0 ]]; then echo -e "$red\0Failed to run dump$nm"; exit 1; fi

coverage report -m
codecov
python-codacy-coverage -r coverage.xml
