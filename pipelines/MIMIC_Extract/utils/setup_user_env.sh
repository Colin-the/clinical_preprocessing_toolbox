#!/bin/bash
# Upstream's environment setup for the bare-metal `make build_curated_from_psql`
# route: source it, then run make from utils/.
#
# Not used by this fork — the Apptainer and Docker paths set their own
# environment. Left as upstream wrote it, which means DBUSER is still their
# username and HOST is a machine that doesn't exist here. Edit both before
# sourcing, and pass the password as $1:
#
#     source utils/setup_user_env.sh <password>
#
# The relative paths also assume mimic-code is checked out as a sibling two
# levels up, which it isn't in this repo.

export MIMIC_CODE_DIR=$(realpath ../../mimic-code)
export MIMIC_EXTRACT_CODE_DIR=$(realpath ../)

export MIMIC_DATA_DIR=$MIMIC_EXTRACT_CODE_DIR/data/

export MIMIC_EXTRACT_OUTPUT_DIR=$MIMIC_DATA_DIR/curated/
mkdir -p $MIMIC_EXTRACT_OUTPUT_DIR

export DBUSER=bnestor
export DBNAME=mimic
export SCHEMA=public,mimiciii
export HOST=mimic
export DBSTRING="dbname=$DBNAME options=--search_path=$SCHEMA"
alias psql="psql -h $HOST -U $DBUSER "

export PGHOST=$HOST
export PGUSER=$DBUSER

export PGPASSWORD=$1
