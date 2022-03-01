from setuptools import setup

with open('requirements.txt') as f:
    install_requires = f.read().splitlines()

setup(
  name='srtgen',
  #packages=['srtgen'],
  version='0.1.0',
  description='Generate subtitles for video file',
  author='Milan Hauth',
  author_email='milahu@gmail.com',
  install_requires=install_requires,
  scripts=[
    'srtgen.py',
  ],
  entry_points={
    #'console_scripts': ['srtgen=srtgen:main'] # No module named 'srtgen'
  },
)
