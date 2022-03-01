{
  pkgs ? import <nixpkgs> {}
}:

let
  python = pkgs.python3;
  fetchPypi = python.pkgs.fetchPypi;
  buildPythonPackage = python.pkgs.buildPythonPackage;
  lib = pkgs.lib;
  fetchFromGitHub = pkgs.fetchFromGitHub;

  # TODO contribute to nixpkgs
  SpeechRecognition = buildPythonPackage rec {
    pname = "SpeechRecognition";
    version = "3.8.1.20220209";
    src = fetchFromGitHub {
      owner = "Uberi";
      repo = "speech_recognition";
      sha256 = "NeKqwIQmzFGhQmzYA4YGM5jXm8koTcmV3O4MfbEZ2V4=";
      rev = "d7b26b45dcebe26dac1f5f518d4a352b56a67465";
    };
    propagatedBuildInputs = (with python.pkgs; [
      pyaudio # PyAudio
      pkgs.flac
    ]);
    doCheck = false; # error: No Default Input Device Available
    checkInputs = with python.pkgs; [
    ];
    # TODO
    # flac-win32.exe
    # flac-linux-x86
    # flac-mac
    postInstall = ''
      echo replacing flac binary
      rm -v $out/lib/python3.9/site-packages/speech_recognition/flac-*
      ln -v -s ${pkgs.flac}/bin/flac $out/lib/python3.9/site-packages/speech_recognition/flac-linux-x86_64
    '';
    meta = with lib; {
      homepage = "https://github.com/Uberi/speech_recognition";
      description = "Library for performing speech recognition, with support for several engines and APIs, online and offline";
      license = licenses.bsdOriginal;
    };
  };

  python-packages = pp: with pp; [
    google-cloud-speech
    setuptools # workaround https://github.com/NixOS/nixpkgs/pull/162173
    SpeechRecognition
    pydub
  ]; 
  python-with-packages = python.withPackages python-packages;
in

python-with-packages.env
