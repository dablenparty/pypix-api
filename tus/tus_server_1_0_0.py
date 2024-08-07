#####################################################################
#   FasTUS - A TUS-Compliant Resumable File Upload Server
#   Author: Jordan Michaels
#   License: Unlicense / Public Domain
#            https://opensource.org/license/unlicense/
#   Contact: fastus@utdream.anonaddy.com
#   Description:
#       The TUS protocol provides a mechanism for resumable file
#       uploads via HTTP/1.1 and HTTP/2. This TUS server implentation
#       is intended to be compatible with TUS clients such as the
#       'uppy' JS client as well as system-native clients.
#   References:
#       TUS Protocol: https://tus.io/protocols/resumable-upload
#       Uppy JS Docs: https://uppy.io/docs/
#       hashlib: https://docs.python.org/3/library/hashlib.html
#       HTTP Status Codes:
#           https://developer.mozilla.org/en-US/docs/Web/HTTP/Status
#####################################################################

import os
import re
import json
import base64
import shutil
import hashlib  # md5 and sha hashlibs
import string, random
import concurrent.futures
from typing import Union
from pydantic import BaseModel
from datetime import datetime, timedelta
from starlette.responses import FileResponse
from fastapi import APIRouter, Header, Request, Response, HTTPException, status, middleware
from fastapi.responses import Response, StreamingResponse
from fastapi.routing import APIRoute
from uuid import UUID, uuid4
from starlette.requests import ClientDisconnect

# local
from api.core.logger import logger
from api.core.db import Base, Engine, Session, TusFiles
from api.core import mime_types
from api.core import settings

# init logger
logger = logger()

# init db
session = Session()
Base.metadata.create_all(Engine)

# init mime_types
mt = mime_types.MimeTypes()

class TusFileRecord(BaseModel):
    uuid: str
    upload_length: Union[int, None] = None
    upload_offset: Union[int, None] = None
    upload_length_deferred: Union[bool, None] = None
    upload_concatenation: Union[bool, None] = None
    upload_concat_id_list: Union[str, None] = None
    upload_metadata: Union[str, None] = None
    upload_complete: Union[bool, None] = False
    upload_lts_path: Union[str, None] = None

class TusServer:
    def __init__(self):
        self.tus_version = ("1.0.0")
        self.tus_extensions = ("creation,creation-defer-length,creation-with-upload,concatination,expiration,termination")
        self.tus_supported_checksums = ("md5,sha1,sha224,sha256,sha384,sha512,sha3_224,sha3_256,sha3_384,sha3_512")
        self.tus_expire = settings.env("TUS_EXPIRE")  # number of minutes before an upload expires
        self.upload_prefix = settings.env("TUS_UPLOAD_PREFIX")  # added to the beginning of upload files
        self.tus_api_prefix = settings.env("TUS_API_PREFIX")  # used with router and building callback url
        self.router = APIRouter(prefix=self.tus_api_prefix)
        self.dir_work = settings.env('DIR_WORK')  # tmp directory for uploads
        self.dir_media = settings.env('DIR_MEDIA')  # final location for uploaded media
        self.file_match_policy = settings.env('TUS_FILE_MATCH_POLICY')  # RENAME or REPLACE
        self.file_sort_policy = settings.env('TUS_FILE_SORT_POLICY') == "True"  # sort uploads based on mime_types?
        self.max_file_size = int(settings.env('TUS_MAX_FILE_SIZE'))
        self.max_req_size = int(settings.env('TUS_MAX_REQ_SIZE'))

        # init routes
        self.set_routes()

    def set_routes(self):
        # GET - Removes expired upload files
        # intended to be hit by a scheduled process
        @self.router.get("")
        async def run_remove_expired_uploads(
            response: Response
        ):
            logger.info(f"TUS GET endpoint hit...")
            self.remove_expired_uploads()

            response.headers["Tus-Version"] = self.tus_version
            response.status_code = 204  # No Content
            return response

        # OPTIONS - Fetch what server supports
        @self.router.options("")
        async def fetch_server_options(
            response: Response
        ):
            logger.info(f"TUS OPTIONS endpoint hit...")
            response.headers["Content-Length"] = str(self.max_req_size)
            response.headers["Tus-Version"] = self.tus_version
            response.headers["Tus-Max-Size"] = str(self.max_file_size)
            response.headers["Tus-Extension"] = self.tus_extensions
            response.headers["Tus-Checksum-Algorithm"] = self.tus_supported_checksums
            response.status_code = 204  # No Content
            return response
        
        # POST - Create new upload file
        @self.router.post("")
        async def create_new_upload(
            request: Request,
            response: Response,
            upload_metadata: str = Header(None),  # kwargs with base64 values
            upload_length: int = Header(None),  # size in bytes of entire upload
            upload_defer_length: int = Header(None),  # value must be 1. indicates "upload_length" will be sent later.
            upload_concat: str = Header(None),  # will be set to 'partial' if this is a concatination upload
            upload_checksum: str = Header(None),  # algorithm + value; ie: "sha1 Kq5sNclPz7QV2+lfQIuc6R7oRu0="
            content_length: int = Header(None),
            content_type: str = Header(None),  # must be "application/offset+octet-stream"
        ):
            logger.info("TUS POST endpoint hit...")
            logger.debug(f"Request.headers: {request.headers}")
            # verify upload_defer_length
            upload_length_deferred = False
            if upload_defer_length != None and upload_defer_length != 1:
                raise HTTPException(status_code=400, detail="Invalid Upload-Defer-Length Request Header. Value must be 1 or not exist.")
            elif upload_defer_length != None and upload_defer_length == 1:
                upload_length_deferred = True
            
            # verify upload concatination
            upload_concatenation = False
            if upload_concat != None and "partial" not in upload_concat and "final;" not in upload_concat:
                raise HTTPException(status_code=400, detail="Invalid Upload-Concat Request Header. Value must be 'partial', 'final', or not exist.")
            elif upload_concat != None and upload_concat == "partial":
                upload_concatenation = True
            elif upload_concat != None and "final;" in upload_concat:
                response = self.process_concat(request, response, upload_metadata, upload_concat)
                return response
            
            # verify upload_length
            if upload_length == None and upload_defer_length == None:
                raise HTTPException(status_code=400, detail="Missing both Upload-Length and Upload-Defer-Length and at least one of these must be present.")
            
            # verify upload_length is less than max_file_size
            if upload_length != None and upload_length > self.max_file_size:
                logger.warning(f"Upload-Length ({upload_length}) is larger than max_file_size ({self.max_file_size}). Return 413.")
                raise HTTPException(status_code=413) # Payload too large

            # verify content_type
            if content_type != None and content_type != "application/offset+octet-stream":
                logger.warning(f"Content-Type ({content_type}) is not 'application/offset+octet-stream' Return 415.")
                raise HTTPException(status_code=400, detail="Invalid Content-Type Request Header. If present value must be 'application/offset+octet-stream'.")

            # verify checksum if present
            tus_checksum_algorithm = None
            tus_checksum_string = None
            if upload_checksum != None and upload_checksum == "":
                logger.warning(f"Upload Checksum header present but no value was passed. Return 460.")
                raise HTTPException(status_code=460)  # Checksum Mismatch
            # make sure checksum value only contains 1 space (between algorithm and value)
            elif upload_checksum != None and upload_checksum.strip().count(" ") == 1:
                tus_checksum_algorithm = upload_checksum.strip().split(" ",1)[0]
                tus_checksum_string = upload_checksum.strip().split(" ",1)[1]
            
            # verify tus_checksum_algorithm
            if tus_checksum_algorithm != None:
                if not tus_checksum_algorithm in self.tus_supported_checksums:
                    logger.warning(f"The requested checksum algorithm ({tus_checksum_algorithm}) is not supported. Return 460")
                    raise HTTPException(status_code=460)  # Checksum Mismatch
            
            # verify the checksum string and algorithm match
            if tus_checksum_string != None and tus_checksum_algorithm != None:
                if not self.is_valid_checksum(tus_checksum_string, tus_checksum_algorithm):
                    logger.warning(f"Checksum string ({tus_checksum_string}) is not a valid checksum for the algorithm ({tus_checksum_algorithm}). Return 460")
                    raise HTTPException(status_code=460)  # Checksum Mismatch

            # create a hex-based uuid to track our in-process upload file
            hex_uuid = str(uuid4().hex)

            # if this is not a concat upload, make sure meta data checks out
            parsed_upload_metadata = {}
            if not upload_concatenation:
                # turn any metadata values into plain text so it can be saved to the metadata record
                # metadata format should be: "filename {base64-utf8_file_name},filetype {base64-utf8_mime_type}"
                logger.debug(f"Request metadata: {upload_metadata}")
                if upload_metadata != None and upload_metadata != "":
                    # meta data exists, parse it out
                    parsed_upload_metadata = self.parse_meta_data(upload_metadata)

            # Create new TusFileRecord object:
            tus_file_record = TusFileRecord(
                uuid = hex_uuid,
                upload_length = upload_length,
                upload_offset = 0,
                upload_length_deferred = upload_length_deferred,
                upload_concatenation = upload_concatenation,
                upload_metadata = json.dumps(parsed_upload_metadata),
            )

            # create new binary file
            self.create_new_upload_file(hex_uuid)
            
            # create new file record for new hex_uuid
            self.create_file_record(hex_uuid, tus_file_record)

            # if post has data, stream data to file
            if (
                content_length != None and
                upload_length != None and
                not upload_length_deferred and
                content_type == "application/offset+octet-stream"
                ):
                await self.write_stream_to_file(request, hex_uuid, tus_checksum_string, tus_checksum_algorithm)

            # update the offset since we uploaded data
            upload_offset = self.fetch_binary_file_size(hex_uuid)

            # compare upload_offset with upload_length to see if file upload is complete
            if tus_file_record.upload_length == upload_offset:
                logger.debug(f"File record upload length ({tus_file_record.upload_length}) matches upload offset ({upload_offset}). Upload is complete.")
                
                # if upload is part of a concat upload, keep it in work directory, otherwise save it to long-term-storage
                if not tus_file_record.upload_concatenation:
                    # get binary file path
                    fn = self.fetch_binary_file_path(hex_uuid)

                    # verify mime type of completed file
                    file_mime_type = mt.get_mime_type(fn)
                    logger.debug(f"File ({fn}) mime type determined as: '{file_mime_type}'")
                    if not mt.is_supported_mime(file_mime_type):
                        # not a supported mime-type, remove the uuid
                        self.remove_uuid(hex_uuid)
                        logger.warning(f"Mime type '{file_mime_type}' is not a supported mime type. Return 415.")
                        raise HTTPException(status_code=415)  # Unsupported Media Type
                    
                    # supported mime type, fetch a file name to save as:
                    lts_file_name = self.fetch_lts_file_name(hex_uuid, file_mime_type)

                    # save file to long-term storage
                    logger.debug(f"Saving file for ({hex_uuid}) to {lts_file_name}.")
                    self.pre_file_complete(hex_uuid)
                    self.save_lts_file(hex_uuid, lts_file_name)
                    self.post_file_complete(hex_uuid)
                    logger.debug("File saved.")

                    # update file record
                    tus_file_record.upload_offset = upload_offset
                    tus_file_record.upload_complete = True
                    tus_file_record.upload_lts_path = lts_file_name
                    self.update_file_record(hex_uuid, tus_file_record)
                else:
                    # part of a concat, so mark as complete and leave in work dir
                    tus_file_record.upload_offset = upload_offset
                    tus_file_record.upload_complete = True
                    self.update_file_record(hex_uuid, tus_file_record)
            else:
                logger.debug(f"File upload length ({tus_file_record.upload_length}) doesn't match upload offset ({upload_offset}). File incomplete.")
                if upload_offset != 0:
                    # simply update the offset since data was included
                    tus_file_record.upload_offset = upload_offset
                    self.update_file_record(hex_uuid, tus_file_record)
            
            # build response headers
            response.headers["Location"] = self.fetch_local_url(request, hex_uuid)
            response.headers["Tus-Resumable"] = self.tus_version
            response.headers["Upload-Offset"] = str(upload_offset)
            response.status_code = 201  # 201 Created

            return response
        
        @self.router.head("/{uuid}")
        async def get_file_info(
            request: Request,
            response: Response,
            uuid:str,
        ):
            logger.info("TUS HEAD endpoint hit...")
            # verify passed uuid is a valid uuid
            if not self.is_valid_uuid4(uuid):
                logger.warning(f"Missing or Invalid uuid: {uuid}. Return 400.")
                raise HTTPException(status_code=400, detail="Missing or Invalid UUID.")

            # get existing file record
            file_record = self.fetch_file_record(uuid)
            if file_record == None:
                logger.warning(f"Method fetch_file_record returned nothing. Return 404.")
                raise HTTPException(status_code=404)
            
            # retrieve the offset
            upload_offset = self.fetch_binary_file_size(uuid)
            
            # assemble response headers
            response.headers["Tus-Resumable"] = self.tus_version
            response.headers["Upload-Offset"] = str(upload_offset)
            response.headers["Cache-Control"] = "no-store"
            response.headers["Content-Length"] = str(self.max_req_size)
            response.status_code = status.HTTP_204_NO_CONTENT

            if file_record.upload_length_deferred:
                response.headers["Upload-Defer-Length"] = str(1)
            else:
                response.headers["Upload-Length"] = str(file_record.upload_length)
            return response
        
        @self.router.get("/{uuid}")
        async def get_file_binary(
            request: Request,
            response: Response,
            uuid:str,
        ):
            logger.info("TUS GET/uuid endpoint hit...")
            # verify passed uuid is a valid uuid
            if not self.is_valid_uuid4(uuid):
                logger.warning(f"Missing or Invalid uuid: {uuid}. Return 400.")
                raise HTTPException(status_code=400, detail="Missing or Invalid UUID.")

            # get existing file record
            file_record = self.fetch_file_record(uuid)
            if file_record == None:
                logger.warning(f"Method fetch_file_record returned nothing. Return 404.")
                raise HTTPException(status_code=404, detail="File doesn't exist, has expired, or has been moved to long-term storage.")
            
            if file_record.complete:
                file_path = file_record.upload_lts_path
            else:
                # stream the file belonging to the passed hex_uuid back to the user if it hasn't expired
                file_path = self.fetch_binary_file_path(uuid)

            if not os.path.exists(file_path):
                logger.warning(f"File record exists but no matching file on the file system. Return 404.")
                raise HTTPException(status_code=404, detail="File doesn't exist, has expired, or has been moved to long-term storage.")

            # guess the mime_type
            file_mime = mt.get_mime_type(file_path)

            def stream_file():
                with open(file_path, mode="rb") as file_stream:
                    yield from file_stream
            
            return StreamingResponse(stream_file(), media_type=file_mime)
        
        @self.router.patch("/{uuid}")
        async def resume_existing_upload(
            request: Request,
            response: Response,
            uuid: str,
            upload_length: int = Header(None),  # size in bytes of entire upload
            upload_offset: int = Header(None),  # size in bytes of what's already been uploaded
            upload_checksum: str = Header(None),  # algorithm + value; ie: "sha1 Kq5sNclPz7QV2+lfQIuc6R7oRu0="
            content_type: str = Header(None),  # must be "application/offset+octet-stream"
        ):
            logger.info("TUS PATCH endpoint hit...")
            # TODO Concatination

            # verify passed uuid is a valid uuid
            if not self.is_valid_uuid4(uuid):
                logger.warning(f"Missing or Invalid uuid: {uuid}. Return 400.")
                raise HTTPException(status_code=400, detail="Missing or Invalid UUID.")

            # verify content_type
            if content_type != None and content_type != "application/offset+octet-stream":
                logger.warning(f"Content-Type Header ({content_type}) is not 'application/offset+octet-stream' Return 415.")
                raise HTTPException(status_code=415)  # Unsupported Media Type

            # verify upload_offset
            if upload_offset == None or upload_offset < 0:
                logger.warning(f"Upload-Offset Header ({upload_offset}) is Missing or < 0. Return 400.")
                raise HTTPException(status_code=400, detail="Missing or Invalid Upload-Offset Request Header.")
            
            # verify upload_offset matches local file offset
            file_offset = self.fetch_binary_file_size(uuid)

            if file_offset == None:
                logger.warning(f"Method fetch_binary_file_size returned nothing. Return 404.")
                raise HTTPException(status_code=404)  # File Not Found
            if file_offset != int(upload_offset):
                logger.warning(f"Current file size ({file_offset}) does not match Request offset ({upload_offset}). Return 409.")
                raise HTTPException(status_code=409)  # Conflict

            # get the file record so we can check if we need "upload_length"            
            file_record = self.fetch_file_record(uuid)
            if file_record == None:
                logger.warning(f"Method fetch_file_record returned nothing. Return 404.")
                raise HTTPException(status_code=404)  # File Not Found

            # verify upload_length
            if upload_length == None:
                # make sure offset value is not deferred
                if file_record.upload_length_deferred:
                    # if offset is deferred with no upload_length supplied, throw error. We need to know completed file size.
                    logger.warning(f"Offset is deferred and no upload_length is defined. We need a completed file size! Return 400.")
                    raise HTTPException(status_code=400, detail="Missing Upload-Length Header.")
            elif upload_length != None and upload_length > self.max_file_size:
                logger.warning(f"Upload-Length ({upload_length}) is larger than max_file_size ({self.max_file_size}). Return 413.")
                raise HTTPException(status_code=413) # Payload too large
            elif upload_length != None and upload_length > 0 and file_record.upload_length_deferred:
                # upload_length is no longer deferred. update file record.
                file_record.upload_length = upload_length
                file_record.upload_length_deferred = False
                logger.debug(f"Saving updated file_record: {json.dumps(file_record)}")
                self.update_file_record(hex_uuid=uuid, filedata=file_record)

            # verify checksum if present
            tus_checksum_algorithm = None
            tus_checksum_string = None
            if upload_checksum != None and upload_checksum == "":
                logger.warning(f"Upload Checksum header present but no value was passed. Return 460.")
                raise HTTPException(status_code=460)  # Checksum Mismatch
            # make sure checksum value only contains 1 space (between algorithm and value)
            elif upload_checksum != None and upload_checksum.strip().count(" ") == 1:
                tus_checksum_algorithm = upload_checksum.strip().split(" ",1)[0]
                tus_checksum_string = upload_checksum.strip().split(" ",1)[1]
            
            # verify tus_checksum_algorithm
            if tus_checksum_algorithm != None:
                if not tus_checksum_algorithm in self.tus_supported_checksums:
                    logger.warning(f"The requested checksum algorithm ({tus_checksum_algorithm}) is not supported. Return 460")
                    raise HTTPException(status_code=460)  # Checksum Mismatch
            
            # verify the checksum string and algorithm match
            if tus_checksum_string != None and tus_checksum_algorithm != None:
                if not self.is_valid_checksum(tus_checksum_string, tus_checksum_algorithm):
                    logger.warning(f"Checksum string ({tus_checksum_string}) is not a valid checksum for the algorithm ({tus_checksum_algorithm}). Return 460")
                    raise HTTPException(status_code=460)  # Checksum Mismatch

            # resume upload
            logger.debug(f"Waiting for chunk to upload...")
            await self.write_stream_to_file(request, uuid, tus_checksum_string, tus_checksum_algorithm)

            # refresh file_offset value after upload
            file_offset = self.fetch_binary_file_size(uuid)

            # compare upload_offset with upload_length to see if file upload is complete
            if file_record.upload_length == file_offset:
                logger.debug(f"File record upload length ({file_record.upload_length}) matches current file offset ({file_offset}). Upload is complete.")
          
                # if upload is part of a concat upload, keep it in work directory, otherwise save it to long-term-storage
                if not file_record.upload_concatenation:
                    # get binary file path
                    fn = self.fetch_binary_file_path(uuid)

                    # verify mime type of completed file
                    file_mime_type = mt.get_mime_type(fn)
                    logger.debug(f"File ({fn}) mime type determined as: '{file_mime_type}'")
                    if not mt.is_supported_mime(file_mime_type):
                        # not a supported mime-type, remove the uuid
                        self.remove_uuid(uuid)
                        logger.warning(f"Mime type '{file_mime_type}' is not a supported mime type. Return 415.")
                        raise HTTPException(status_code=415)  # Unsupported Media Type
                    
                    # supported mime type, fetch a file name to save as:
                    lts_file_name = self.fetch_lts_file_name(uuid, file_mime_type)

                    # save file to long-term storage
                    logger.debug(f"Saving file for ({uuid}) to {lts_file_name}.")
                    self.pre_file_complete(uuid)
                    self.save_lts_file(uuid, lts_file_name)
                    self.post_file_complete(uuid)
                    logger.debug("File saved.")

                    # update file record
                    file_record.upload_offset = file_offset
                    file_record.upload_complete = True
                    file_record.upload_lts_path = lts_file_name
                    self.update_file_record(uuid, file_record)
                else:
                    # part of a concat, so mark as complete and leave in work dir
                    file_record.upload_offset = file_offset
                    file_record.upload_complete = True
                    self.update_file_record(uuid, file_record)
            else:
                # simply update the offset
                file_record.upload_offset = file_offset
                self.update_file_record(uuid, file_record)

            # build response headers
            response.headers["Tus-Resumable"] = self.tus_version
            response.headers["Upload-Offset"] = str(file_offset)
            response.headers["Upload-Expires"] = str(file_record.time_expires)
            response.status_code = 204  # No Content

            return response
    
        @self.router.delete("/{uuid}")
        async def delete_current_upload(
            response: Response,
            uuid: str,
            upload_length: int = Header(None),  # size in bytes of entire upload
            upload_offset: int = Header(None),  # size in bytes of what's already been uploaded
            content_length: int = Header(None),
        ):
            logger.info("TUS DELETE endpoint hit...")

            # verify passed uuid is a valid uuid
            if not self.is_valid_uuid4(uuid):
                logger.warning(f"Missing or Invalid uuid: {uuid}. Return 400.")
                raise HTTPException(status_code=400, detail="Missing or Invalid UUID.")

            # verify file record exists        
            file_record = self.fetch_file_record(uuid)
            if file_record == None:
                logger.warning(f"No file record exists for this file. Return 404.")
                raise HTTPException(status_code=404)  # File Not Found
            
            # file record found, remove file record and files
            self.pre_file_termination(uuid)
            self.remove_uuid(uuid)
            self.post_file_termination(uuid)

            # build response headers
            response.headers["Tus-Resumable"] = self.tus_version
            response.status_code = 204  # No Content

            return response


    # use fastAPI's middleware ability to check for a TUS 'X-HTTP-Method-Override' header
    async def method_override_check(self, request: Request, call_next):
        # if the "X-HTTP-Method-Override" method is present
        if "X-HTTP-Method-Override" in request.headers:
            logger.info(f"Found 'X-HTTP-Method-Override' in list of request headers. Verifying...")
            # assign the header value to a changable variable
            new_method = request.headers["X-HTTP-Method-Override"]
            # make sure value is one of the TUS supported methods
            if new_method in ("GET", "POST", "DELETE", "PATCH", "OPTIONS", "HEAD"):
                logger.info(f"Method override successful. Request method will be changed from '{request.method}' to '{new_method}'")
                # if it's supported go ahead and assign it to the request
                request.method = new_method
            else:
                raise HTTPException(status_code=400, detail="Missing or invalid X-HTTP-Method-Override request header.")
        # continue processing request with updated method
        response = await call_next(request)
        return response

    async def write_stream_to_file(self, request: Request, hex_uuid:str, upload_checksum:str = None, checksum_algorithm:str = None):
        # build stream file name for this uuid
        fn = self.fetch_binary_stream_path(hex_uuid)

        # create empty binary stream file to stream to
        open(fn, "x").close()

        # stream upload data to stream file
        try:
            logger.debug(f"Streaming data to file... ")
            async for data in request.stream():
                with open(fn, 'ab') as f:
                    f.write(data)
        except ClientDisconnect:
            # log it and be done
            logger.error('Client disconnected.')
        except Exception as err:
            # log it and let client know
            logger.error('Exception occurred during upload process: {0}'.format(err))
            raise HTTPException(status_code=500, detail="Exception occurred during file streaming process. Please check server logs.")
        logger.debug("Finished streaming.")

        # see if we have checksum values
        if upload_checksum != None and checksum_algorithm != None:
            if not self.is_valid_file_checksum(fn, upload_checksum, checksum_algorithm):
                os.remove(fn)
                logger.warning(f"Checksum validation error. Return 460")
                raise HTTPException(status_code=460)  # Checksum Mismatch

        pf = self.fetch_binary_file_path(hex_uuid)
        # open the stream file in read-binary mode
        with open(fn, 'rb') as file_stream:
            # open the partial file in append-binary mode
            with open(pf, 'ab') as partial_file:
                # stream the file_stream file to the partial file in 4k chunks
                chunk_size = 4096
                while True:
                    data = file_stream.read(chunk_size)
                    if not data:
                        break
                    partial_file.write(data)
        # now that the stream has been appended to the partial file, we can remove the stream file
        os.remove(fn)

        # get existing file record
        file_record = self.fetch_file_record(hex_uuid)

        # set new file size offset
        logger.debug(f"Setting new file_size offset...")
        file_record.upload_offset = str(self.fetch_binary_file_size(hex_uuid))

        # save updated file record
        logger.debug(f"Saving updated file_record: {file_record}")
        self.update_file_record(hex_uuid=hex_uuid, filedata=file_record)

    def fetch_tus_version(self):
        return self.tus_version
    
    def fetch_file_record(self, hex_uuid:str):
        logger.debug(f"Retrieving file record for file UUID: {hex_uuid}")
        file_session = session.query(TusFiles)
        file_query = file_session.filter(TusFiles.uuid==UUID(hex=hex_uuid))
        file_record = file_query.first()
        if file_record == None:
            logger.debug(f"No record found for UUID: {hex_uuid}.")
            return None
        logger.debug(f"Found file record for {hex_uuid}")
        return file_record
    
    def fetch_binary_file_path(self, hex_uuid:str):
        binary_file = f"{self.upload_prefix}{hex_uuid}.part"
        file_path = os.path.join(self.dir_work, hex_uuid, binary_file)
        logger.debug(f"Binary file path built as: {file_path}")
        return file_path
    
    def fetch_binary_stream_path(self, hex_uuid:str):
        logger.debug(f"Fetching binary stream path for file UUID: {hex_uuid}")
        binary_stream = f"{self.upload_prefix}{hex_uuid}.stream"
        file_path = os.path.join(self.dir_work, hex_uuid, binary_stream)
        logger.debug(f"Binary stream path built as: {file_path}")
        return file_path

    def create_upload_folder(self, hex_uuid:str):
        logger.debug(f"Creating upload folder for file UUID: {hex_uuid}")
        # build the new folder path
        file_dir = os.path.join(self.dir_work, hex_uuid)
        logger.debug(f"Upload folder built as: {file_dir}")
        
        # make sure the path doesn't exist before we create it
        if not os.path.exists(file_dir):
            try:
                logger.debug(f"Attempting to create file directory: {file_dir}")
                os.mkdir(file_dir)
            except Exception as err:
                # log it and let client know
                logger.error('Exception occurred during upload process: {0}'.format(err))
                raise HTTPException(status_code=500, detail="Exception occurred attempting to create new file upload. Please try again.")
            if os.path.exists(file_dir):
                logger.debug(f"Work directory '{file_dir}' created successfully.")
        else:
            # should not happen, but if it does for some reason, toss an error and ask user to try again.
            logger.error(f"The '{file_dir}' directory already exists!")
            raise HTTPException(status_code=500, detail="Exception occurred attempting to create new file upload. Please try again.")

    def create_new_upload_file(self, hex_uuid:str):
        # create new upload folder
        self.create_upload_folder(hex_uuid)

        # fetch full path to binary file
        fn = self.fetch_binary_file_path(hex_uuid)
        
        # create the empty file
        try:
            logger.debug(f"Attempting to create empty file: {fn}")
            open(fn, "x").close()
        except Exception as err:
            # log it and let client know
            logger.error('Exception occurred during upload process: {0}'.format(err))
            raise HTTPException(status_code=500, detail="Exception occurred attempting to create new file upload. Please try again.")
        if os.path.exists(fn):
            logger.debug(f"The empty file '{fn}' was created successfully.")
        return
    
    def create_file_record(self, hex_uuid:str, filedata:TusFileRecord):
        logger.debug("Creating new file record...")
        if filedata.upload_length != None:
            logger.debug(f"filedata.upload_length: {filedata.upload_length}")
        if filedata.upload_offset != None:
            logger.debug(f"filedata.upload_offset: {filedata.upload_offset}")
        if filedata.upload_length_deferred != None:
            logger.debug(f"filedata.upload_length_deferred: {filedata.upload_length_deferred}")
        if filedata.upload_concatenation != None:
            logger.debug(f"filedata.upload_concatenation: {filedata.upload_concatenation}")
        if filedata.upload_concat_id_list != None:
            logger.debug(f"filedata.upload_concat_id_list: {filedata.upload_concat_id_list}")
        if filedata.upload_metadata != None:
            logger.debug(f"filedata.upload_metadata: {filedata.upload_metadata}")
        file_record = TusFiles(
            uuid = UUID(hex=hex_uuid),
            upload_length = filedata.upload_length,
            upload_offset = filedata.upload_offset,
            upload_length_deferred = bool(filedata.upload_length_deferred),
            upload_concatenation = bool(filedata.upload_concatenation),
            upload_concat_id_list = filedata.upload_concat_id_list,
            upload_metadata = filedata.upload_metadata,  # save python dict as JSON
        )
        logger.debug(f"File_record created as: {file_record}")
        logger.debug(f"Saving file record:")
        session.add(file_record)
        session.commit()
        logger.debug("ORM transaction complete.")
    
    def update_file_record(self, hex_uuid:str, filedata:TusFileRecord):
        logger.debug(f"making sure file record exists before attempting to update it...")
        file_record = self.fetch_file_record(hex_uuid)
        if file_record == None:
            logger.error(f"Cannot process file update without a file record!")
            raise HTTPException(status_code=500, detail="Exception occurred while updating file record. Please review logs.")
        
        # process update
        logger.debug("Updating file record...")
        file_record.upload_length = filedata.upload_length
        file_record.upload_offset = filedata.upload_offset
        file_record.upload_length_deferred = bool(filedata.upload_length_deferred)
        file_record.upload_concatenation = bool(filedata.upload_concatenation)
        file_record.upload_metadata = filedata.upload_metadata
        file_record.upload_complete = bool(filedata.upload_complete)
        file_record.upload_lts_path = filedata.upload_lts_path
        logger.debug(f"Updated file record built as: {file_record}")
        session.add(file_record)
        session.commit()
        logger.debug("ORM transaction complete.")
    
    def read_binary_file(self, hex_uuid:str):
        # fetch full path to binary file
        fn = self.fetch_binary_file_path(hex_uuid)
        if os.path.exists(fn):
            with open(fn, 'rb') as f:
                return f.read()
        # otherwise return nothing
        return None
    
    def fetch_binary_file_size(self, hex_uuid:str):
        # fetch full path to binary file
        fn = self.fetch_binary_file_path(hex_uuid)
        if os.path.exists(fn):
            file_size = os.path.getsize(fn)  # returns value in bytes
            logger.debug(f"File size reported as: {file_size} bytes.")
            return file_size
        else:
            logger.warning(f"Binary file does not exist for uuid: {hex_uuid}. Return 404.")
            raise HTTPException(status_code=404)  # File Not Found   
    
    def fetch_local_url(self, request:Request, hex_uuid:str):
        # defaults
        proto = "http"  # unlikely to be doing local SSL termination
        host = request.headers.get("host")
        # check if we're behind a proxy like Nginx
        if request.headers.get("X-Forwarded-Proto") is not None:
            proto = request.headers.get("X-Forwarded-Proto")
        if request.headers.get("X-Forwarded-Host") is not None:
            host = request.headers.get("X-Forwarded-Host")
        local_url = f"{proto}://{host}{self.tus_api_prefix}/{hex_uuid}"
        logger.debug(f"Local URL built as: {local_url}")
        return local_url
    
    def is_valid_uuid4(self, hex_uuid:str = None):
        if hex_uuid != None:
            try:
                uuid_obj = UUID(hex=hex_uuid)
                return uuid_obj.version == 4  # will return boolean
            except (ValueError, TypeError):
                pass  # ignore errors
        return False  # default to False
    
    def parse_meta_data(self, metadata_input):
        parsed_metadata = {}
        # turn any metadata values into plain text so it can be saved to the metadata record
        # metadata format should be: "filename {base64-utf8_file_name},filetype {base64-utf8_mime_type}"
        logger.debug(f"Processing metadata: {metadata_input}")
        # verify 'filename' is present in metadata
        if 'filename' not in metadata_input:
            logger.warning(f"'filename' missing from metadata header. Return 400.")
            raise HTTPException(status_code=400, detail="Missing 'filename' attribute in metadata.")
        # verify 'filetype' is present in metadata
        if 'filetype' not in metadata_input:
            logger.warning(f"'filetype' missing from metadata header. Return 400.")
            raise HTTPException(status_code=400, detail="Missing 'filetype' attribute in metadata.")
        # verify there's at least one comma (minimum filename and filetype fields)
        if ',' not in metadata_input:
            logger.warning(f"Improperly formatted metadata. Return 400.")
            raise HTTPException(status_code=400, detail="Improperly formatted metadata.")
        try:
            # loop over each key/value pair
            for line in metadata_input.split(","):
                logger.debug(f"Processing metadata line: {line}")
                k, v = line.split(" ", 1)
                txt_value = base64.b64decode(v.strip()).decode("utf-8")
                # add the decoded value to our parsed_metadata
                parsed_metadata[k.strip()] = txt_value
        except Exception as err:
            logger.warning("Exception parsing metadata: {}. Return 400.".format(err))
            raise HTTPException(status_code=400, detail="Improperly formatted metadata.")
        logger.debug(f"Parsed metadata decoded to: {parsed_metadata}")

        # verify 'filename' present in metadata
        if 'filename' not in parsed_metadata:
            logger.warning(f"'filename' missing from metadata header. Return 400.")
            raise HTTPException(status_code=400, detail="Missing 'filename' attribute in metadata.")
        
        # verify 'filetype' present in metadata
        if 'filetype' not in parsed_metadata:
            logger.warning(f"'filetype' missing from metadata header. Return 400.")
            raise HTTPException(status_code=400, detail="Missing 'filetype' attribute in metadata.")

        # verify passed 'content-type' is allowed by server (verified on the file itself after upload as well)
        if not mt.is_supported_mime(parsed_metadata['filetype']):
            logger.warning(f"Client is attempting to upload an unsupported content type: {parsed_metadata['content-type']}. Return 415.")
            raise HTTPException(status_code=415) # Unsupported Media Type
        
        # parsing complete
        return parsed_metadata

    def process_concat(self,
        request:Request,
        response:Response,
        upload_metadata: str = Header(None),  # kwargs with base64 values
        upload_concat: str = Header(None),  # will be set to 'partial' if this is a concatination upload
        ):
        # parse the concat header for the list of file id's
        s = upload_concat.replace("final;", "")

        # Split the string into a list using space as the delimiter
        file_id_list = s.split(" ")

        # build the URL prefix so we can remove it from the passed ID's
        proto = "http"  # unlikely to be doing local SSL termination
        host = request.headers.get("host")
        # check if we're behind a proxy like Nginx
        if request.headers.get("X-Forwarded-Proto") is not None:
            proto = request.headers.get("X-Forwarded-Proto")
        if request.headers.get("X-Forwarded-Host") is not None:
            host = request.headers.get("X-Forwarded-Host")
        local_url = f"{proto}://{host}{self.tus_api_prefix}/"

        # Remove the URL from each id so only the id is left
        file_id_list = [value.replace(local_url, "") for value in file_id_list]
        logger.debug(f"File ID list parsed as: {json.dumps(file_id_list)}")

        # validate each file id
        for uuid in file_id_list:
            file_record = self.fetch_file_record(uuid)
            if file_record == None:
                logger.warning(f"Method fetch_file_record returned nothing. Return 404.")
                raise HTTPException(status_code=404, detail="File doesn't exist, has expired, or has been moved to long-term storage.")
        
        # parse meta data
        parsed_upload_metadata = {}
        logger.debug(f"Request metadata: {upload_metadata}")
        if upload_metadata != None and upload_metadata != "":
            # meta data exists, parse it out
            parsed_upload_metadata = self.parse_meta_data(upload_metadata)
        
        # create a hex-based uuid to track this final file id
        hex_uuid = str(uuid4().hex)

        # Create new TusFileRecord object:
        tus_file_record = TusFileRecord(
            uuid = hex_uuid,
            upload_offset = 0,
            upload_metadata = json.dumps(parsed_upload_metadata),
            upload_concatenation = True,
            upload_concat_id_list = json.dumps(file_id_list),
            upload_complete = False
        )

        logger.debug(f"TusFileRecord.upload_concat_id_list: {json.dumps(tus_file_record.upload_concat_id_list)}")
        
        # create new file record for new hex_uuid
        self.create_file_record(hex_uuid, tus_file_record)

        # a good TUS client would have done a TUS HEAD check to make
        # sure that all file parts have finished, but just in case,
        # make sure all parts have finished before compiling them.
        uploads_complete = True
        for uuid in file_id_list:
            file_record = self.fetch_file_record(uuid)
            if not file_record.upload_complete:
                logger.warning(f"Client requested concatenation assembly for {hex_uuid} before file part {file_record.uuid} had finished uploading.")
                uploads_complete = False

        if uploads_complete:
            logger.debug(f"File uploading for file id {hex_uuid} complete.")
            # run pre file complete hook
            self.pre_file_complete(hex_uuid)
            # concatinate the file using a background task
            # with concurrent.futures.ThreadPoolExecutor() as executor:
            #     logger.debug(f"Running concat process...")
            #     bg_concat_proc = executor.submit(self.assemble_concat, hex_uuid)
            self.assemble_concat(hex_uuid)
            # run post file complete hook
            self.post_file_complete(hex_uuid)
        
        # build response headers
        response.headers["Location"] = self.fetch_local_url(request, hex_uuid)
        response.headers["Tus-Resumable"] = self.tus_version
        if not uploads_complete:
            response.headers["Tus-Extension"] = "concatenation-unfinished"
        response.status_code = 201  # 201 Created

        return response

    def assemble_concat(self, hex_uuid):
        logger.debug(f"Attempting to assemble concatenated file {hex_uuid}...")

        # pull up the file record
        file_record = self.fetch_file_record(hex_uuid)
        if file_record == None:
            logger.error(f"Method fetch_file_record returned nothing. Unable to concatenate.")
        else:
            logger.debug(f"File record found for file id {hex_uuid}...")
        
        # verify record is a concat list record
        if not file_record.upload_concatenation:
            logger.error(f"File record is not a concatenation file record. Unable to concatenate.")
        
        # make sure we have a valid concat uuid list
        if not file_record.upload_concat_id_list or file_record.upload_concat_id_list == "":
            logger.error(f"File record is not a concatenation file record. Unable to concatenate.")
        
        # try to load the list from JSON
        try:
            file_id_list = json.loads(file_record.upload_concat_id_list)
        except Exception as err:
            logger.error(f"Error trying to read ID values from JSON: {str(err)}. Unable to concatenate.")
        
        # make sure all uploads are complete before assembling them
        file_path_list = []
        uploads_complete = True
        for uuid in file_id_list:
            temp_fr = self.fetch_file_record(uuid)
            if not temp_fr.upload_complete:
                logger.warning(f"Client requested concatenation assembly for {hex_uuid} before file part {temp_fr.uuid} had finished uploading.")
                uploads_complete = False
            else:
                file_path_list.append(self.fetch_binary_file_path(uuid))
        
        if not uploads_complete:
            logger.error(f"Not all upload parts have completed. Unable to concatenate.")
        
        # get upload_metadata filetype
        file_metadata = json.loads(file_record.upload_metadata)
        filetype = file_metadata["filetype"]

        # generate lts file name
        lts_path = self.fetch_lts_file_name(hex_uuid, filetype)
        logger.debug(f"Long term storage path built as: {lts_path}")

        # loop over file_path_list and concatinate files
        logger.debug("Starting file concatenation...")
        with open(lts_path, 'wb') as merged_file:
            for fpath in file_path_list:
                with open(fpath, 'rb') as part_file:
                    logger.debug(f"Merging {part_file} into {merged_file}")
                    bdata = part_file.read()
                    merged_file.write(bdata)
        
        # save lts file path to file record
        file_record.upload_lts_path = lts_path
        logger.debug(f"Concatenation file id {hex_uuid} concatenated to: {lts_path}")

        # mark the concatination as complete
        file_record.upload_complete = True
        
        # save file record
        self.update_file_record(hex_uuid, file_record)

    def remove_uuid(self, hex_uuid:str):
        # clean out work files
        self.clean_uuid(hex_uuid)

        # pull up existing file record
        file_session = session.query(TusFiles)
        file_query = file_session.filter(TusFiles.uuid==UUID(hex=hex_uuid))
        file_record = file_query.first()

        # remove file record for uuid
        session.delete(file_record)
        session.commit()

        logger.info(f"UUID {hex_uuid} successfully removed.")
    
    # clears out work files for a completed file uuid
    def clean_uuid(self, hex_uuid:str):
        logger.info(f"Removing work files for uuid: {hex_uuid}")
        # build the directory path that would be used for this uuid
        file_dir = os.path.join(self.dir_work, hex_uuid)
        logger.debug(f"File directory built as: {file_dir}")

        # recursively remove upload directory for uuid
        if os.path.exists(file_dir):
            shutil.rmtree(file_dir)
            logger.debug(f"Directory {file_dir} removed successfully.")
        else:
            logger.debug(f"Directory {file_dir} does not exist.")

        logger.info(f"Work files for {hex_uuid} successfully removed.")

    # build and return usable long-term storage (lts) path
    def fetch_lts_file_name(self, hex_uuid:str, mime:str = None):
        logger.debug("Building long-term storage file name...")
        # get the current file record
        file_record = self.fetch_file_record(hex_uuid)
        logger.debug(f"Current file record retrieved: {file_record}")

        # separate passed mime type: "video/mp4" -> ['video', 'mp4']
        subfolder = re.split('/', mime)[0]  # 'video'
        file_extension = re.split('/', mime)[1]  # 'mp4'
        logger.debug(f"file_sort_policy set to: {self.file_sort_policy}")
        if self.file_sort_policy:
            if not os.path.exists(os.path.join(self.dir_media, subfolder)):
                try:
                    os.mkdir(os.path.join(self.dir_media, subfolder))
                except Exception as err:
                    logger.error('Exception occurred creating mime directory: {0}'.format(err))
                    # revert to no sorting
                    subfolder = ""
        else:
            # no sorting, no subfolder
            subfolder = ""

        logger.debug(f"subfolder identified as: {subfolder}")
        logger.debug(f"file_extension identified as: {file_extension}")

        # isolate filname from extension: myfile.mpeg -> 'myfile'
        logger.debug(f"attempting to isolate filename in: {file_record.upload_metadata}")
        # convert json string to python dict
        dict_upload_metadata = json.loads(file_record.upload_metadata)
        # isolate requested filename value
        tmp_file_name = dict_upload_metadata['filename']
        logger.debug(f"found filename in metadata: {tmp_file_name}")
        # split file extension from requested filename
        file_name = os.path.splitext(tmp_file_name)[0]
        logger.debug(f"file name identified as: {file_name}")

        # concatinate file_name with correct mime type extension: myfile -> myfile.mp4
        full_file_name = file_name + '.' + file_extension
        logger.debug(f"Full file name built as: {full_file_name}")

        # create long-term storage file path
        lts_path = os.path.join(self.dir_media, subfolder, full_file_name)
        logger.debug(f"Initial file path built as: {lts_path}")

        # check if file path exists already
        if os.path.exists(lts_path):
            logger.debug(f"LTS file path exists! {lts_path}")
            if self.file_match_policy == "RENAME":
                logger.debug(f"Proceeding with policy: {self.file_match_policy}")
                while os.path.exists(lts_path):
                    rand_file_name = file_name + '-' + self.fetch_rand_string() + '.' + file_extension
                    lts_path = os.path.join(self.dir_media, subfolder, rand_file_name)
                    logger.debug(f"RENAME file path built as: {lts_path}")
                    return lts_path
            elif self.file_match_policy == "REPLACE":
                logger.debug(f"Proceeding with policy: {self.file_match_policy}")
                # simply remove the previous file before saving the new file
                os.remove(lts_path)
                return lts_path
        else:
            return lts_path
    
    def fetch_rand_string(self, size=10, chars=string.ascii_uppercase + string.digits):
        return ''.join(random.choice(chars) for _ in range(size))

    def save_lts_file(self, hex_uuid:str, fpath:str):
        logger.debug(f"Attempting to save binary file to long-term storage path: {fpath}")
        # fetch full path to binary file
        binary_file = self.fetch_binary_file_path(hex_uuid)
        
        # move/rename the file
        try:
            os.rename(binary_file, fpath)
        except Exception as err:
            logger.error(f'Attempted to save binary file to {fpath} and received error: {err}')
            return
        logger.debug("File saved successfully.")

        # remove expired files
        logger.debug("Checking expired files...")
        self.remove_expired_uploads()

    def remove_expired_uploads(self):
        # pull up expired file upload records
        time_now = datetime.utcnow()
        file_session = session.query(TusFiles)
        file_query = file_session.filter(TusFiles.time_expires<time_now)
        expired_records = file_query.all()

        # loop over expired records and remove each one
        for r in expired_records:
            str_uuid = str(r.uuid)
            logger.debug(f"str+uuid: {str_uuid}")
            hex_uuid = str_uuid.replace('-', '')
            self.pre_file_expire(hex_uuid)
            logger.debug(f"Removing uuid '{hex_uuid}' which expired on '{r.time_expires}' and it is now '{time_now}'")
            self.remove_uuid(hex_uuid)
            self.post_file_expire(hex_uuid)

    def is_valid_checksum(self, checksum_string, algorithm):
        checksum_lengths = {
            "md5": 32,
            "sha1": 40,
            "sha224": 56,
            "sha256": 64,
            "sha384": 96,
            "sha512": 128,
            "sha3_224": 56,
            "sha3_256": 64,
            "sha3_384": 96,
            "sha3_512": 128,
        }

        # Check the length
        if len(checksum_string) != checksum_lengths[algorithm]:
            return False

        # Check the characters using a regular expression
        if not re.match(r'^[0-9a-fA-F]*$', checksum_string):
            return False

        return True

    def is_valid_file_checksum(self, file_path, checksum, algorithm):
        logger.debug(f"Performing file checksum on file: {file_path}, using {algorithm}, with checksum: {checksum}")
        # loop over the potentially very large file in small, 8k (8192 bytes)
        # chunks in order to reach the final checksum of the stream that was
        # uploaded
        chunk_size=8192

        # open the file in read-binary mode
        with open(file_path, "rb") as f:
            # Create a hashlib 'hasher' constructor to keep track of the chunk hashes
            # https://docs.python.org/3/library/hashlib.html#hashlib.new
            hasher = hashlib.new(algorithm)
            # loop over the file so we can hash it in chunks
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                # update our hasher with new chunk data so we don't have to load
                # the entire file into memory
                # https://docs.python.org/3/library/hashlib.html#hashlib.hash.update
                hasher.update(data)
            # deliver the final computed checkum value to check it against the
            # value that was provided by the upload client. We need it in hex.
            # https://docs.python.org/3/library/hashlib.html#hashlib.hash.hexdigest
            computed_hex_checksum = hasher.hexdigest()

        # Compare the computed hex checksum against the provided checksum
        # and respond accordingly.
        logger.debug(f"Computed checksum is: {computed_hex_checksum} vs provided checksum of: {checksum}")
        if computed_hex_checksum == checksum:
            logger.debug("Comparison matches. Returning True")
            return True
        else:
            logger.debug("Comparison mismatch. Returning False")
            return False

    # runs just before file is moved to long-term storage
    def pre_file_complete(self, hex_uuid):
        pass
    
    # runs just after file is moved to long-term storage
    def post_file_complete(self, hex_uuid):
        pass

    # runs just before uuid folder is removed from work directory
    def pre_file_expire(self, hex_uuid):
        pass

    # runs just after uuid folder is removed from work directory
    def post_file_expire(self, hex_uuid):
        pass

    # runs just before uuid folder is removed from work directory
    def pre_file_termination(self, hex_uuid):
        pass

    # runs just after uuid folder is removed from work directory
    def post_file_termination(self, hex_uuid):
        pass