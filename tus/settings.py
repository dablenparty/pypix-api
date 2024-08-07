#####################################################################
#   FasTUS Settings File
#   Author: Jordan Michaels
#   License: Unlicense / Public Domain
#            https://opensource.org/license/unlicense/
#   Contact: fastus@utdream.anonaddy.com
#   Description:
#       Initializes and validates the .env file.
#####################################################################

import os
import re
import sys
import getpass
from dotenv import load_dotenv

# make sure .env file exists
if not os.path.isfile("./.env"):
    sys.exit("ERROR: \n" + \
        "Missing or invalid environment file.\n" + \
        "Please create a .env file using the env-example.txt file before running this program.\n" + \
        "\n" + \
        "Example commands:\n" + \
        "$ cp env-eample.txt .env\n" + \
        "$ nano .env\n" + \
        "\n" + \
        "Use CTRL+X to exit Nano once you're done editing.\n")

# load .env file
load_dotenv()

# we use getenv since it will default to None if var doesn't exist
env = os.getenv

# initialize environment variable file
def init_env():

    # Create variable groups using lists so that we can verify them as groups
    # Application Variables
    app_vars = []
    app_vars.append("APP_NAME")
    app_vars.append("APP_VERSION")
    app_vars.append("APP_SUMMARY")
    app_vars.append("APP_DESCRIPTION")
    app_vars.append("APP_AUTHOR")
    app_vars.append("APP_AUTHOR_URL")
    app_vars.append("APP_AUTHOR_EMAIL")
    app_vars.append("APP_LIC_NAME")
    app_vars.append("APP_LIC_IDENT")
    app_vars.append("APP_LIC_URL")
    # Directory Variables
    dir_vars = []
    dir_vars.append("DIR_HOME")
    dir_vars.append("DIR_MEDIA")
    dir_vars.append("DIR_WORK")
    # TUS Variables
    tus_vars = []
    tus_vars.append("TUS_VERSION")
    tus_vars.append("TUS_EXPIRE")
    tus_vars.append("TUS_API_PREFIX")
    tus_vars.append("TUS_UPLOAD_PREFIX")
    tus_vars.append("TUS_MAX_FILE_SIZE")
    tus_vars.append("TUS_MAX_REQ_SIZE")
    tus_vars.append("TUS_FILE_SORT_POLICY")
    tus_vars.append("TUS_FILE_MATCH_POLICY")
    # CORS Variables
    cors_vars = []
    cors_vars.append("CORS_ORIGINS")
    cors_vars.append("CORS_METHODS")
    cors_vars.append("CORS_HEADERS")
    cors_vars.append("CORS_CREDENTIALS")
    # Logging Variables
    log_vars = []
    log_vars.append("LOG_NAME")
    log_vars.append("LOG_DIR")
    log_vars.append("LOG_FORMAT")
    log_vars.append("LOG_DAYS")
    log_vars.append("LOG_LEVEL")
    log_vars.append("LOG_SIZE")
    # SQLite Variables
    db_vars = []
    db_vars.append("DB_SQLITE_URL")


    # BEGIN validation tests
    
    for v in app_vars:
        if env(v) == None:
            os.environ(v) == ""  # default to empty string

    for v in dir_vars:
        value = env(v)
        if value == "" or value == None:
            sys.exit(f"'{v}' must have a value.")
        if not re.match(r"^[a-zA-Z0-9_/-]+$", v):
            sys.exit(f"'{v}' value must be alphanumeric with only the following exceptions: '-', '_', or '/'.")
        if not os.path.exists(value):
            sys.exit(f"'{v}' directory must exist.")
        if not os.access(value, os.W_OK):
            sys.exit(f"'{v}' directory must be writable by the '{getpass.getuser()}' user.")

    for v in tus_vars:
        value = env(v)
        if value == "" or value == None:
            sys.exit(f"'{v}' must have a value.")
        if v == "TUS_EXPIRE":
            try:
                int(value)
            except ValueError:
                sys.exit(f"'{v}' value must be an integer.")
            if not int(value) > 0:
                sys.exit(f"'{v}' value must be greater than 0.")
        if v == "TUS_API_PREFIX":
            if not isinstance(value, str):
                sys.exit(f"'{v}' value must be a string.")
            if not value.startswith("/"):
                sys.exit(f"'{v}' value must start with a '/'.")
            if not re.match(r"^[a-zA-Z0-9_/-]+$", v):
                sys.exit(f"'{v}' value must be alphanumeric with only the following exceptions: '-', '_', or '/'.")
        if v == "TUS_UPLOAD_PREFIX":
            if not isinstance(value, str):
                sys.exit(f"'{v}' value must be a string.")
            if not re.match(r"^[a-zA-Z0-9_./-]+$", v):
                sys.exit(f"'{v}' value must be alphanumeric with only the following exceptions: '-', '.', '_', or '/'.")
        if v in ["TUS_MAX_FILE_SIZE","TUS_MAX_REQ_SIZE"]:
            try:
                int(value)
            except ValueError:
                sys.exit(f"'{v}' value must be an integer.")
            if not int(value) > 0:
                sys.exit(f"'{v}' value must be greater than 0.")
        if v == "TUS_FILE_SORT_POLICY":
            try:
                env(v) == bool(value)
            except ValueError:
                sys.exit(f"'{v}' value must be a boolean.")
        if v == "TUS_FILE_MATCH_POLICY":
            if value not in ["RENAME", "REPLACE"]:
                sys.exit(f"'{v}' value must be either 'RENAME' or 'REPLACE'.")

    for v in cors_vars:
        if v != "CORS_CREDENTIALS" and env(v) == None:
            env(v) == ["*"]  # default to allow all
        elif v == "CORS_CREDENTIALS" and env(v) == None:
            env(v) == True  # default to allow CORS cookies

    for v in log_vars:
        value = env(v)
        if value == "":
            sys.exit(f"'{v}' must have a value.")
        if v == "LOG_DIR":
            if not os.path.exists(value):
                sys.exit(f"'{v}' directory must exist.")
            if not os.access(value, os.W_OK):
                sys.exit(f"'{v}' directory must be writable by the '{getpass.getuser()}' user.")
        if v in ["LOG_DAYS", "LOG_SIZE"]:
            try:
                int(value)
            except ValueError:
                sys.exit(f"'{v}' value must be an integer.")
            if not int(value) > 0:
                sys.exit(f"'{v}' value must be greater than 0.")
        if v == "LOG_LEVEL":
            if value not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
                sys.exit(f"'{v}' value must be one of the following: 'DEBUG, INFO, WARNING, ERROR, CRITICAL'")
    
    for v in db_vars:
        value = env(v)
        if v == "DB_SQLITE_URL":
            if value == "":
                env(v) == "sqlite:///fastus.db"  # default to home directory

# only init once
def init():
    init_env()