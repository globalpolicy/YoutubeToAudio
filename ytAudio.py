import argparse
import requests
import urllib.parse
import os
import json
import time
from jsinterp import JSInterpreter
import re

DECRYPTOR_FUNCTION_CACHE = None


# file = open("base.js", "r")
# jsCode = file.read()
# file.close()
#
# regexSearchList = [r'(["\'])signature\1\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(',
#                    r'\.sig\|\|(?P<sig>[a-zA-Z0-9$]+)\(',
#                    r'yt\.akamaized\.net/\)\s*\|\|\s*.*?\s*c\s*&&\s*d\.set\([^,]+\s*,\s*(?:encodeURIComponent\s*\()?(?P<sig>[a-zA-Z0-9$]+)\(',
#                    r'\bc\s*&&\s*d\.set\([^,]+\s*,\s*(?:encodeURIComponent\s*\()?\s*(?P<sig>[a-zA-Z0-9$]+)\(',
#                    r'\bc\s*&&\s*d\.set\([^,]+\s*,\s*\([^)]*\)\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\('
#                    ]
# for regexSearchStr in regexSearchList:
#     regexSearchResult = re.search(regexSearchStr, jsCode)
#     if regexSearchResult is not None:
#         functionName = regexSearchResult.groupdict()['sig']
#         break
# if functionName is not None:
#     jsInt = JSInterpreter(jsCode)
#     decoderFunction = jsInt.extract_function(functionName)
#     encodedSignature = '77C77C77C04B5D3FA05AEB6D87D3D6DDB38C37D0CA04F0.32014708C1262F13436CCF3DB788575DD19879B4444'
#     decodedSignature = decoderFunction([encodedSignature])
#     print(decodedSignature)
#
# exit(0)


def retrieveSignatureDecryptorFunction(ytplayerConfigJson):
    global DECRYPTOR_FUNCTION_CACHE
    if DECRYPTOR_FUNCTION_CACHE is not None:
        return DECRYPTOR_FUNCTION_CACHE

    assetsJson = ytplayerConfigJson['assets']
    try:
        print(
            "Video seems to use signature protection...\nAttempting extraction of decryptor from video player asset...\n\n")
        jsplayer = assetsJson['js']  # This key may not exist if video uses swf player
        print("JSPlayer identified as the video player asset. Downloading JSPlayer javascript file...\n\n")
        jsplayerUrl = "https://www.youtube.com" + jsplayer
        jsplayerContent = requests.get(jsplayerUrl).text
        print("Asset downloaded. Extracting decryption function...\n\n")
        # This list is directly taken from youtube-dl's source - youtube.py
        # It contains regex filters to find the name of the decryption function in the jsplayer file.
        # The idea is that at least one filter from the list will match
        regexSearchList = [r'(["\'])signature\1\s*,\s*(?P<sig>[a-zA-Z0-9$]+)\(',
                           r'\.sig\|\|(?P<sig>[a-zA-Z0-9$]+)\(',
                           r'yt\.akamaized\.net/\)\s*\|\|\s*.*?\s*c\s*&&\s*d\.set\([^,]+\s*,\s*(?:encodeURIComponent\s*\()?(?P<sig>[a-zA-Z0-9$]+)\(',
                           r'\bc\s*&&\s*d\.set\([^,]+\s*,\s*(?:encodeURIComponent\s*\()?\s*(?P<sig>[a-zA-Z0-9$]+)\(',
                           r'\bc\s*&&\s*d\.set\([^,]+\s*,\s*\([^)]*\)\s*\(\s*(?P<sig>[a-zA-Z0-9$]+)\('
                           ]
        decryptionFunctionName = None
        for regexSearchStr in regexSearchList:
            regexSearchResult = re.search(regexSearchStr, jsplayerContent)
            if regexSearchResult is not None:
                decryptionFunctionName = regexSearchResult.groupdict()['sig']
                break
        if decryptionFunctionName is None:
            print("Cannot find signature-decryption function in JSPlayer asset!")
            exit(1)
        jsInt = JSInterpreter(jsplayerContent)
        decryptionFunction = jsInt.extract_function(decryptionFunctionName)  # Returns an invokable decryption function
        print("Signature-decryption function found. Deciphering encrypted signature...\n\n")
        DECRYPTOR_FUNCTION_CACHE = decryptionFunction
        return decryptionFunction

    except KeyError:
        print("ytplayer.config.assets.js doesn't exist.\nProbably swf player?")
        exit(1)


SMALL = False
LARGE = False

argparser = argparse.ArgumentParser(description='Retrieve audio files from youtube link')
group = argparser.add_mutually_exclusive_group()
group.add_argument('-s', '--small', action='store_true', help='Small file')
group.add_argument('-l', '--large', action='store_true', help='Large file')
argparser.add_argument('url', help='Youtube URL')

args = vars(argparser.parse_args())
URL = args['url']
if args['small']:
    SMALL = True
else:
    LARGE = True

webpageContent = requests.get(URL).text
ytplayerConfigString = webpageContent[
                       webpageContent.index('ytplayer.config = ') + 18:webpageContent.index('ytplayer.load') - 1]
ytplayerConfigJson = json.loads(ytplayerConfigString)
ytArgs = ytplayerConfigJson['args']
videoTitle = ytArgs['title']
player_responseString = ytArgs['player_response']
player_responseJson = json.loads(player_responseString)
streamingDataJson = player_responseJson['streamingData']
adaptiveFormats = []
try:
    adaptiveFormats = streamingDataJson['adaptiveFormats']
except KeyError:
    print(
        "adaptiveFormats key not present in ytplayer.config.args.player_response.streamingData\nUsing ytplayer.config.args.adaptive_fmts\n\n")
    adaptiveFormatsString = ytArgs['adaptive_fmts']
    tokens = adaptiveFormatsString.split(',')
    for token in tokens:
        params = token.split('&')
        adaptiveFormat = {}
        for param in params:
            tmp = param.split('=')
            key = tmp[0]
            value = tmp[1]
            if key == 'type':
                adaptiveFormat['mimeType'] = urllib.parse.unquote(value)
            if key == 'clen':
                adaptiveFormat['contentLength'] = value
            if key == 'url':
                adaptiveFormat['url'] = urllib.parse.unquote(value)
            if key == 's':
                # Presence of the param 's' in lieu of the param 'signature' indicates an encrypted-signature video
                # Must decrypt the value of 's' and add to the url as 'signature' before downloading
                signDecryptor = retrieveSignatureDecryptorFunction(ytplayerConfigJson)
                decryptedSignature = signDecryptor([value])  # Important to note the function expects a list
        try:
            adaptiveFormat['url'] += f'&signature={decryptedSignature}'
        except NameError:  # decryptedSignature variable doesn't exist meaning no encryption
            pass
        adaptiveFormats.append(adaptiveFormat)

longest_audio_length = 0
longest_audio_index = 0
shortest_audio_length = float('inf')
shortest_audio_index = 0
for index, format in enumerate(adaptiveFormats):
    mimeType = format['mimeType']
    if 'audio/' in mimeType:
        if int(format['contentLength']) > longest_audio_length:
            longest_audio_length = int(format['contentLength'])
            longest_audio_index = index
        if int(format['contentLength']) < shortest_audio_length:
            shortest_audio_length = int(format['contentLength'])
            shortest_audio_index = index

if LARGE:
    index = longest_audio_index
else:
    index = shortest_audio_index
adaptiveFormat = adaptiveFormats[index]
audioUrl = adaptiveFormat['url']
audioUrl = urllib.parse.unquote(audioUrl)
mimeType = adaptiveFormat['mimeType']
fileType = mimeType[mimeType.index('/') + 1: mimeType.index(';')]

filename = "".join(x for x in videoTitle if x not in r'<>?*%:\/|"') + "." + fileType

req = requests.get(audioUrl, stream=True)
contentLength = int(req.headers['Content-Length'])
downloadedlength = 0
chunksize = 1024
_previousDlRate = 0
_previousTime = 0
headers = {}
if os.path.isfile(filename): os.remove(filename)
with open(filename, 'ab') as file:
    _before = time.time()
    print("Starting audio download...\n\n")
    while downloadedlength < contentLength:
        headers['Range'] = f'bytes={downloadedlength}-{downloadedlength + chunksize - 1}'
        _previousTime = time.time()
        req = requests.get(audioUrl, headers=headers, stream=True)
        file.write(req.content)
        downloadedPacketSize = int(req.headers['Content-Length'])
        downloadedlength += downloadedPacketSize
        _nowTime = time.time()
        _currentDlRate = downloadedPacketSize / (_nowTime - _previousTime)
        if _currentDlRate > _previousDlRate:
            chunksize = int(chunksize * 2 if chunksize < 4 * 1024 * 1024 else chunksize)
        elif _currentDlRate < _previousDlRate:
            chunksize = int(chunksize / 1.1 if chunksize > 1 else chunksize)
        _previousDlRate = _currentDlRate
        print(f'Current chunksize = {chunksize}')
        print(f'Current download rate = {"{:.2f}".format(_currentDlRate / (1024 * 1024))} MB/s')
        print("{:.2f}".format(downloadedlength / (1024 * 1024)) + ' MB - ' + "{:.2f}".format(
            downloadedlength / contentLength * 100) + '%')

    elapsedSeconds = time.time() - _before
    print(f'\nDownload complete in {"{:.2f}".format(elapsedSeconds)}s')
