#####################################################################
#   FasTUS Mime Type testing and support.
#   Author: Jordan Michaels
#   License: Unlicense / Public Domain
#            https://opensource.org/license/unlicense/
#   Contact: fastus@utdream.anonaddy.com
#   Description:
#       These methods exist to test the files that are uploaded to
#       your FasTUS server and verify that they are the mime types
#       you expect and want on your server.
#
#       Mime-types are separated into parent groups (audio, video,
#       image etc) to give you and your application the ability to
#       limit your testing to specific groups if you want. For
#       example, in addition to the example media groups below, you
#       could add an "application" mime type group that could be
#       used to test for PDF's or documents; ie: "application/pdf".
#       Grom there, you could create an "is_supported_application()"
#       method and limit your mime type checking to just the
#       application mime types. Useful!
#       
#   Docs:
#       https://mimetype.io/all-types
#       https://www.freeformatter.com/mime-types-list.html
#####################################################################

import os
import magic

# local
from api.core import settings
from api.core.logger import logger

# init logger
logger = logger()

class MimeTypes:
 
    def __init__(self):
                
        self.audio_types = [
            "audio/aac",
            "audio/ogg",
            "audio/oga", # ogg audio
            "audio/mpeg",
            "audio/webm",
            "audio/wave",
            "audio/wav",
        ]

        self.video_types = [
            "video/mp4",
            "video/mpeg",
            "video/ogg",
            "video/ogv", # ogg video
            "video/jpeg", # .jpgv - jpeg video
            "video/x-msvideo", # avi
            "video/webm",
            "video/x-matroska", # mkv
        ]

        self.image_types = [
            "image/jpeg",
            "image/pjpeg", # progressive jpeg
            "image/png",
            "image/apng", # animated png
            "image/avif", # avi image
            "image/gif",
            "image/webp",
            "image/svg+xml", # svg
        ]

    def is_supported_mime(self, mt:str = None):
        if not mt:
            return False

        all_types = self.audio_types + self.video_types + self.image_types

        if mt in all_types:
            return True
        else:
            return False

    def is_supported_audio(self, mt:str = None):
        if not mt:
            return False

        if mt in self.audio_types:
            return True
        else:
            return False

    def is_supported_video(self, mt:str = None):
        if not mt:
            return False

        if mt in self.audio_types:
            return True
        else:
            return False

    def is_supported_image(self, mt:str = None):
        if not mt:
            return False

        if mt in self.image_types:
            return True
        else:
            return False
    
    def get_mime_type(self, file_path:str = None):
        logger.debug('Executing get_mime_type() method.')
        # make sure a file to test was passed
        if not file_path:
            logger.debug('Missing or invalid file path. Returning None.')
            return None

        # make sure the media file exists
        if not os.path.isfile(file_path):
            logger.warning(f'Passed file ({file_path}) does not exist. Returning None.')
            return None
        
        return magic.from_file(file_path, mime=True)