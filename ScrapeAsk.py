import requests
import time
import os
import errno
import sys
from bs4 import BeautifulSoup
from contextlib import closing
from enum import Enum, unique

# arbitrary timeout time. suggested multiple of 3 plus a little
TIMEOUT_TIME = 30.5

# can recoginize regular images, gifs, uploaded vids, and youtube links
@unique
class MediaType(Enum):
    unknown = 0
    image = 1
    gif = 2
    uploaded_vid = 3
    youtube_vid = 4

# Attempt to create a subdirectory for each username. Doesn't matter is already
# exists. If insufficient permissions, let user know. Other OSErrors raised.
# returns the directory string. if an error during making dir, return None
def create_dir(username):
    path = os.path.dirname(os.path.realpath(sys.argv[0])) # script's location
    directory = path + "/" + username
    try:
        # attempt to make subdirectory (username). if it exists, no error
        os.makedirs(directory, exist_ok=True)
        return directory
    except OSError as e:
        if e.errno == errno.EACCES:
            print("Insufficient permissions to create subdirectory " + directory
                        + "/.", "Try manually creating it.")
            return None
        else:
            raise e
            return None

# attempts to download the image or video. Prefixes filename based on media type.
# file location: script_dir/username/mediaType_pageNumber_imageNumber.origExtension
# page number will go away in future versions
def download_media(directory, url, page, media_cnt, media_type):
    prefix = "/"
    if (media_type == MediaType.image or media_type == MediaType.gif):
        prefix = "/image_"
    elif media_type == MediaType.uploaded_vid:
        prefix = "/vid_"
    elif media_type == MediaType.youtube_vid: # not downloading YT vids, so will never happen
        prefix = "/yt_"
    try:
        # with closing to ensure stream connection always closed
        with closing(requests.get(url, stream=True, timeout=TIMEOUT_TIME)) as r:
            if r.status_code == requests.codes.ok:
                file_loc = directory + prefix + str(page).zfill(3) + "_" \
                            + str(media_cnt).zfill(2) + "." + url.split(".")[-1]
                #DEBUG
                #print("Downloading image", r.url, "to", file_loc)
                # "wb" = open for write and as binary file
                with open(file_loc, "wb") as file:
                    for chunk in r:
                        file.write(chunk)
            else:
                # if media file could not be opened, report status code to user
                print("Could not get media. Status code", r.status_code,
                            "on media", url)
    except requests.exceptions.ConnectionError:
        # if lost connection, report status code to user
        print("Connection error. Status code", r.status_code, "on media", url)

# prints a short error notification to console and increments count of failed
# connections to be handled when limit reached
# def connection_problem(output):
#     NOT_OK_LIMIT = 3 # how many connection failures before quitting program
#     print(output)
#     global not_ok_counter
#     not_ok_counter += 1
#     if not_ok_counter >= NOT_OK_LIMIT:
#         print(NOT_OK_LIMIT, "or more consecutive connection attempts not ok. Aborting.");
#         return False
#     return True

# Determine the type of media based on the different tags and attributes
# Different media have the download URL in different places
# Return a tuple with the correct media type and correct download URL
def check_media(link_url):
    IMAGE_A_ATTR = "data-url"
    GIF_IMG_ATTR = "data-src"
    VID_A_DIV_CLASS = "visualItemPlayIcon-videoAnswer"
    YOUTUBE_A_DIV_CLASS = "visualItemPlayIcon-youTube"

    media_type = MediaType.unknown # Default to unknown

    # find the full-size image url for different media
    # normal image has a specific attribute on the <a> tag
    if link_url.has_attr(IMAGE_A_ATTR):
        link_url = link_url[IMAGE_A_ATTR]
        media_type = MediaType.image
    # animated gifs have a specific attribute on the <img> tag
    elif link_url.img.has_attr(GIF_IMG_ATTR):
        link_url = link_url.img[GIF_IMG_ATTR]
        media_type = MediaType.gif
    # uploaded videos have a <div> tag with a specific class as a child of the <a> tag
    # videos from youtube have a different <div> class, but we don't download those
    elif link_url.div:
        if VID_A_DIV_CLASS in link_url.div["class"]:
            #DEBUG
            # print("UPLOAD:", link_url["href"])
            link_url = link_url["href"]
            media_type = MediaType.uploaded_vid
        elif YOUTUBE_A_DIV_CLASS in link_url.div["class"]:
            #DEBUG
            # print("YOUTUBE:", link_url["href"])
            link_url = link_url["href"] # can't D/L YT, but for completeness
            media_type = MediaType.youtube_vid
    # Other configurations of <img> links aren't checked.
    else:
        #DEBUG
        print("Unknown media : ", link_url)
    #DEBUG
    # print("Image Counter:", img_counter)
    return (media_type, link_url)

def main():
    URL_DOMAIN = "http://ask.fm/"
    URL_PATH = "/answers/more/"
    PAGE_PARAM = "page"
    # arbitrary sleep time. not sure if insufficient, overkill, works ... | 32
    TIME_BETWEEN_PAGE_REQUESTS = 3.1;
    
    page_counter = 0
    total_media_counter = 0 # Used only for final report
    check_next_page = True

    # get target username from user. If empty input, exit program
    username = input("Target username: ")
    if username:
        base_url = URL_DOMAIN + username + URL_PATH
        print("Scraping media from", URL_DOMAIN + username)
        # create subdirectory using username
        directory = create_dir(username)
        # None is returned on failed directory creation, so in that case,
        # don't go to scraping loop
        if directory is None:
            check_next_page = False
    else:
        print ("No name entered.")
        # Don't go to scraping loop if user submitted empty input
        check_next_page = False

    # boolean to be false when ready to close the program (usually connection 
    # failure, either from error or end of account's pages of questions)
    while check_next_page:
        # when there is no internet connection, ConnectionError thrown.
        # Notify user and exit scraping loop
        try:
            req = requests.get(base_url, params={PAGE_PARAM: page_counter},
                                timeout=TIMEOUT_TIME)
        except requests.exceptions.ConnectionError:
            print("Connection error on " + base_url + "?" + PAGE_PARAM + "="
                      + str(page_counter) + ". Check your internet connection.")
            break
        if req.status_code == requests.codes.ok:
            #DEBUG
            #print("Looking for images on", req.url)
            # media counters get reset each page
            img_counter = 0
            vid_counter = 0

            soup = BeautifulSoup(req.content, "html.parser")
            # find all anchor tags to get all links
            link_urls = soup.find_all("a")

            # See which links have an <img> tag. These are the ones we want
            for link_url in link_urls:
                # Skipping iframes because those would give duplicate videos
                if link_url.img and not link_url.iframe:
                    # determine media type and correct download URL
                    media_type, link_url = check_media(link_url)
                    if media_type == MediaType.image or media_type == MediaType.gif:
                        download_media(directory, link_url, page_counter,
                                        img_counter, media_type)
                        img_counter += 1
                        total_media_counter += 1
                    elif media_type == MediaType.uploaded_vid:
                    #elif (media_type == MediaType.uploaded_vid or media_type == MediaType.youtube_vid):
                        download_media(directory, link_url, page_counter,
                                        vid_counter, media_type)
                        vid_counter += 1
                        total_media_counter += 1
            # All image links handled, move to the next page after incr page counter
            page_counter += 1
            #DEBUG
            #print("Sleeping", TIME_BETWEEN_PAGE_REQUESTS, "seconds")
            # Attempt to avoid getting blocked or limited by sleep between page requests
            time.sleep(TIME_BETWEEN_PAGE_REQUESTS)
        else:
            # Status code 204 at end of questions
            # Status code 404 at on invalid username
            # Status code 400 at bad username input (not alphanumeric?)
            print("Status code", req.status_code, "on", req.url)
            # exit scraping loop on bad page request
            check_next_page = False

    #notify user of program exit, telling total media and pages scraped
    print("Scraped", total_media_counter, "media from", page_counter, "pages.")

if __name__ == "__main__":
    main()