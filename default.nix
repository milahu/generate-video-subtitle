/*
nix-build -E 'with import <nixpkgs> { }; callPackage ./default.nix { }'
*/

{
  pkgs ? import <nixpkgs> {}
}:

let
  python = pkgs.python3;
  buildPythonPackage = python.pkgs.buildPythonPackage;
  lib = pkgs.lib;
  fetchFromGitHub = pkgs.fetchFromGitHub;
in

buildPythonPackage rec {
  pname = "srtgen";
  version = "0.1.0";
  src = ./.;
  /*
  src = fetchFromGitHub {
    # https://github.com/milahu/srtgen
    owner = "milahu";
    repo = "srtgen";
    rev = "09322af1dda2a35764ca3652ed5fd1a330a8090d";
    sha256 = ""; # todo
  }
  */
  propagatedBuildInputs = with python.pkgs; [
    pydub
    google-cloud-speech
    setuptools # workaround https://github.com/NixOS/nixpkgs/pull/162173
    #SpeechRecognition
  ];
  postInstall = ''
    mv -v $out/bin/srtgen.py $out/bin/srtgen
  '';
  meta = with lib; {
    homepage = "https://github.com/milahu/srtgen";
    description = "Generate subtitles for video file";
    license = licenses.mit;
  };
}
