Threaded_HTTP_Downloader
========================

A utility to parse and and download all files of an http directory listing.  The parse_remote_dir_tree func recursively
scans each level.  It builds a list of all files and folders at that level.  

This utility expects a raw directory listing.  It will not work if there is a default html page. 

usage: Threaded_HTTP_Downloader.py [-h] [--url DL_URL] [--output OUTPUT_DIR]
                                   [--threads THREADS] [--verbose] [--mirror]
                                   [--debug]

optional arguments: 

  -h, --help           show this help message and exit
  
  --url DL_URL         This is the URL to parse download
  
  --output OUTPUT_DIR  The directory to place downloaded files. Omitting this option will output to CWD
  
  --threads THREADS    The number of download threads to run at once.
  
  --verbose            Prints a more verbose output
  
  --mirror             Only download file if remote file is newer than local
  
  --debug              Print Debug Output
