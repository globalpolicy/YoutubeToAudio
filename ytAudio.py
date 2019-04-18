import argparse
import requests
import urllib.parse
import os
import json
import time

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
        "adaptiveFormats key not present in ytplayer.config.args.player_response.streamingData\nUsing ytplayer.config.args.adaptive_fmts")
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
        os.system('cls')
        print(f'Current chunksize = {chunksize}')
        print(f'Current download rate = {"{:.2f}".format(_currentDlRate / (1024 * 1024))} MB/s')
        print("{:.2f}".format(downloadedlength / (1024 * 1024)) + ' MB - ' + "{:.2f}".format(
            downloadedlength / contentLength * 100) + '%')

    elapsedSeconds = time.time() - _before
    print(f'\nDownload complete in {"{:.2f}".format(elapsedSeconds)}s')
