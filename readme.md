# srtgen

Generate subtitles for video file

Using [Google Cloud Speech-To-Text API](https://cloud.google.com/speech-to-text)

This program requires a Google account and an API key:
[Create project on Google Cloud](https://console.cloud.google.com/projectcreate)

## usage

```
$ ./srtgen.py 
usage
  srtgen.py --apikey path/to/keyfile.json path/to/input-video.mp4

environment variables
  GOOGLE_APPLICATION_CREDENTIALS=path/to/keyfile.json srtgen.py path/to/input-video.mp4

keyfile
  This program requires a Google account and an API key
  https://console.cloud.google.com/projectcreate
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

### based on

* https://github.com/plutowang/generate-video-subtitle
* https://cloud.google.com/speech-to-text/docs/basics

### postprocessing tools

* [subtitleeditor](https://github.com/kitone/subtitleeditor)
* [translatesubtitles.co](https://translatesubtitles.co/)

### similar tools

* https://github.com/topics/subtitles-generator
  * https://github.com/nestyme/Subtitles-generator

## todo

* use `speech_recognition` module
  * we need a service that returns timestamps for every word
    * google cloud speeech: [enable_word_time_offsets=True](https://cloud.google.com/speech-to-text/docs/async-time-offsets)
* automatic postprocessing
  * reduce manual work
  * split long sentences
  * merge short sentences
