# srtgen

Generate subtitles for video file

Using the paid [Google Cloud Speech-To-Text API](https://cloud.google.com/speech-to-text)

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
    * pricing
      * speech recognition needs lots of space and time = there is no free lunch
      * https://cloud.google.com/speech-to-text/pricing#pricing_table
        * first hour is free
          * TODO one hour per month or one hour per google account?
        * Speech Recognition without Data Logging: $0.006 / 15 seconds = $0.024 / 1 minute = about $1.50 / 1 hour
        * Speech Recognition with Data Logging: $0.004 / 15 seconds = $0.016 / 1 minute = about $1.00 / 1 hour
        * Data Logging = feedback of manually corrected text to improve quality of service
          * TODO implement upload of corrected text
    * TODO Automatic punctuation

## related

### based on

* https://github.com/plutowang/generate-video-subtitle
* https://cloud.google.com/speech-to-text/docs/basics

### postprocessing tools

* edit subtitles
  * [aegisub](https://github.com/TypesettingTools/Aegisub)
  * [gaupol](https://github.com/otsaloma/gaupol)
  * [subtitleeditor](https://github.com/kitone/subtitleeditor)
* translate subtitles
  * [translatesubtitles.co](https://translatesubtitles.co/)

### similar tools

* https://github.com/abhirooptalasila/AutoSub
  * using Mozilla DeepSpeech
  * offline speech recognition
    * lower quality than google speech
    * limited by user hardware (space + time)
* https://github.com/topics/subtitles-generator
  * https://github.com/nestyme/Subtitles-generator

## todo

* use `speech_recognition` module, so srtgen can use multiple backend services
  * we need a service that returns timestamps for every word
    * google cloud speeech: [enable_word_time_offsets=True](https://cloud.google.com/speech-to-text/docs/async-time-offsets)
    * alternative: synchronize words and audio waveform
      * https://github.com/otsaloma?tab=stars&q=subtitle
        * https://github.com/smacke/ffsubsync Automagically synchronize subtitles with video.
        * https://github.com/kaegi/alass "Automatic Language-Agnostic Subtitle Synchronization"
* automatic postprocessing
  * reduce manual work
  * split long sentences
  * merge short sentences
