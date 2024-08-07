#####################################################################
#   FasTUS Database Models for SQLAlchemy ORM
#   Author: Jordan Michaels
#   License: Unlicense / Public Domain
#            https://opensource.org/license/unlicense/
#   Contact: fastus@utdream.anonaddy.com
#   Description:
#       The DB tables are used by FasTUS to keep track of the file
#       chunks that have been uploaded.
#####################################################################

from sqlalchemy import URL, create_engine, Column, Integer, String, Text, Boolean, Uuid, DateTime, ForeignKey, Numeric
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base
from datetime import timedelta, datetime

# local
from api.core.logger import logger
from api.core import settings

# init logger
logger = logger()

# init DB
sqlite = settings.env("DB_SQLITE_URL")
Engine = create_engine(sqlite)
Session = sessionmaker(Engine)
Base = declarative_base()

#####################################################################
# TusFiles
#   The 'tus_files' table is where FasTUS keeps track of files being
#   uploaded to the server. Data required by the TUS protocol is also
#   stored here, such as whether the length of the file has been
#   deferred or whether this file upload is to be a concatination
#   file upload.
#
#   uuid
#       The hex UUID for the file being uploaded.
#   upload_length
#       The full size of the intended file in bytes. Used to
#       determine whether a file upload is finished or not.
#   upload_offset
#       The amount of the file in bytes that has been uploaded so far
#   upload_length_deferred
#       Indicates whether the upload_length value is being deferred
#       by the client. Server cannot check to see if file is finished
#       until upload_length is provided.
#   upload_concatenation
#       Indicates whether the upload will be processed in parts using
#       multiple file uploads.
#   upload_concat_id_list
#       The list of uuid's that belong to this concatenated file.
#       Used when a TUS concatenation final request has been sent and
#       all file uploads may not have completed yet.
#   upload_metadata
#       File metadata is stored in JSON format here. Specifically
#       used to store 'filename' and 'filetype' values.
#   upload_complete
#       Boolean value that indicates if the upload has been completed.
#       Useful on files that are not sorted and placed into long-term
#       storage.
#   upload_lts_path
#       Long-Term storage location for completed & sorted uploads.
#   time_created
#       The UTC timestamp of when the file was created.
#   time_updated
#       The UTC timestamp of when the file was last updated.
#   time_expires
#       The UTC timestamp of when the file expires and removed from
#       the file system if the upload is not resumed.
#####################################################################

class TusFiles(Base):
    __tablename__ = 'tus_files'
    uuid                    = Column(Uuid, primary_key=True)
    upload_length           = Column(Integer, nullable=True)
    upload_offset           = Column(Integer, nullable=False, default=0)
    upload_length_deferred  = Column(Boolean, nullable=False, default=False)
    upload_concatenation    = Column(Boolean, nullable=False, default=False)
    upload_concat_id_list   = Column(Text, nullable=True, default=None)
    upload_metadata         = Column(String(200), nullable=False)
    upload_complete         = Column(Boolean, nullable=False, default=False)
    upload_lts_path         = Column(String(512), nullable=True, default=None)
    time_created            = Column(DateTime(timezone=False), server_default=func.now())
    time_updated            = Column(DateTime(timezone=False), onupdate=func.now())
    time_expires            = Column(DateTime(timezone=False), default=datetime.utcnow() + timedelta(minutes=int(settings.env("TUS_EXPIRE"))))