# srtgen

Generate subtitles for video file

Using [Google Cloud Speech-To-Text API](https://cloud.google.com/speech-to-text/docs/languages)

## usage

```
$ ./srtgen.py 
usage:
  srtgen.py --apikey path/to/keyfile.json path/to/input-video.mp4

set keyfile via environment variable:
  GOOGLE_APPLICATION_CREDENTIALS=path/to/keyfile.json srtgen.py path/to/input-video.mp4
```

subtitle is written to stdout and `output/xxxxxx-input-video.mp4/output_file.srt`  
where `xxxxxx` is the sha1 hash of the input video file

temporary files are stored in `output/xxxxxx-input-video.mp4/` 

## features

* workaround size limit in google API
  * no need for Google Cloud Storage = `gs` protocol
  * duration is limited to 60 seconds
  * file size is limited to 10485760 bytes

## dependencies

* ffmpeg
* python
  * pydub
  * google.cloud.speech
    * API key

## related

based on

* https://github.com/plutowang/generate-video-subtitle
* https://cloud.google.com/speech-to-text/docs/basics
