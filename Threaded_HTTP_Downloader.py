import os
import sys
import argparse
import subprocess
import time
import threading
from bs4 import BeautifulSoup
import urllib.request
import urllib.error

# TODO Cleanup handling of slashes
# TODO Add a queue for files to download.  This way while waiting on max threads the download list can continue to build
# TODO Add option for pure urllib download to remove the wget requirement.


"""
A class to parse a directory listing of a URL and spawn a Wget download for each file encountered.
The module uses Beautiful Soup to parse the URL and pull out all links.  The links are then checked
to determine of they are files or directories.  If it's a file a download thread is spawned.  If it's
a directory it crawls into it and repeats the process.

If on Windows script expects the Wget exe to be in the same directory or in util.

The module expects a raw directory listing of the URL. It will not work if there is a default HTML page at the URL.
"""
class ThreadedWget():

    def __init__(self, dl_url, output_dir, threads=15, mirror=False, verbose=False, no_parent=False,
                 no_host_directories=False):

        self.download_url = dl_url
        self.verbose = verbose
        self.threads = int(threads)

        if os.name == 'nt':
            self.host_os = 'windows'
        elif os.name == 'posix':
            self.host_os = 'posix'

        self.clear_screen()

        # Validate The Initial URL
        try:
            urllib.request.urlopen(dl_url)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print('[x] ERROR: Failed to open URL: ', dl_url)
            print('[x] Error Msg: ', e.reason)
            print('\n[x] Please Check URL And Try Again')
            time.sleep(5)
            sys.exit()

        if not output_dir:
            print('[!] No output directory given.  CWD will be used. ')
            response = input('[?] Do You Wish To Proceed? (y/n)')
            if response.lower() == 'n' or response.lower() == 'no':
                print('[!] Please use --output to specify output directory')
                time.sleep(4)
                sys.exit()
            else:
                self.output_dir = os.getcwd()
        else:
            self.output_dir = output_dir

        # Handle Wget Flags
        if not mirror:
            self.mirror = ''
        else:
            self.mirror = '--mirror'

        if not no_parent:
            self.no_parent = ''
        else:
            self.no_parent = '--no-parent'

        if not no_host_directories:
            self.no_host_directories = ''
        else:
            self.no_host_directories = '--no-host-directories'


    def run(self):
        """
        This method executes the actual download.  It calls the parse_remote_dir_tree method and waits for
        it to return.  Once it returns it waits until all download threads have finishes.  Prior to threads
        finishing it prints a list of the files currently being downloaded
        :return:
        """

        print('[+] Starting Parse And Download Of ' + self.download_url + '\n')

        self.parse_remote_dir_tree(self.download_url, '')

        print('\nAll Download Threads Launched.\n')
        # TODO Make thread checking it's down method
        last_active = 0
        while threading.active_count() > 1:
            if last_active != threading.active_count():
                self.clear_screen()
                print('---------- ACTIVE DOWNLOAD THREADS ----------')
                print('The Following ', threading.active_count() - 1, ' files are still downloading')
                for thrd in threading.enumerate():
                    if thrd.name.lower() == 'mainthread':
                        continue
                    print('[+] ', thrd.name)
            last_active = threading.active_count()
            time.sleep(1)

        print('[!] Success: All Downloads Have Finished')

    def parse_remote_dir_tree(self, url, dir, path='', previous=None):
        """
        Crawl a directory listing of a URL and find all files.  Each call of the function builds a
        list of all files and directories at the current level.  It then calls _threaded_download()
        for each file.  It then calls itself again for each directory.
        :param url: The URL to parse. Starts with base url and recursivly calls deeper URL
        :param dir: Current dir at time of calling function. Used to build of new URL
        :param path: Builds of the path of folders crawled into.  Used to build of URL
        :param previous:
        :return:
        """
        dirs = []
        files = []

        # Build up directory path
        # path = path + '/' + dir

        # TODO This is mega hackish.  Revisit
        if path == '/':
            path = path + dir
        else:
            path = path + '/' + dir

        # TODO This is failing on Linux for some dumb reason.
        try:
            response = urllib.request.urlopen(url)
        except (urllib.error.HTTPError, urllib.error.URLError) as e:
            print('[x] ERROR: Failed to open URL: ', url)
            print('[x] Error Msg: ', e.reason)
            return

        parsed_page = BeautifulSoup(response)

        for link in parsed_page.find_all('a'):

            # Avoid climbing back to previous level
            if link.string == '[To Parent Directory]':
                if self.verbose:
                    print('[+] Skipping parent directory')
                continue

            # Get file name and extension.  If directory ext will be None
            name, ext = os.path.splitext(link.string)

            if ext:
                files.append(link.string)
            else:
                dirs.append(link.string)

        for file in files:
            download_url = url + '/' + file

            # Manage the amount of concurrent downloads. Don't start more download threads until below threshold
            while threading.active_count() > self.threads:
                print('[x] Max download threads reached.  Waiting for threads to decrease')
                time.sleep(2)

            output_file = '/' + file

            time.sleep(0.02)
            if self.verbose:
                print('[+] Starting new thread with download_url as: ' + download_url)
                print('[+] Starting new thread with output_file as: ' + output_file)

            t = threading.Thread(target=self._threaded_download, name=os.path.basename(output_file),
                                 args=(download_url, output_file, path,))
            t.start()

        for folder in dirs:
            # First entry can be blank. Skip Iteration
            if not folder:
                continue
            # TODO Don't think this check is needed. Verify. Remove from args if not needed
            if folder == previous:
                continue

            # TODO Hackish?
            # Add trailing slash
            if url[-1:] != '/':
                url += '/'

            if self.verbose:
                print('[+] Calling parse_remote_dir_tree with URL: ' + url + folder)

            next_url = url + folder

            self.parse_remote_dir_tree(next_url, folder, path=path, previous=dir)

    def _threaded_download(self, download_url, output_file, path):
        """
        Construct and call Wget to download individual files
        Wget is being used here as I cannot find a way to easily replicate Wget's mirror functionality via urllib
        :param download_url: The URL to download
        :param output_file: The file name and path of the local file
        :return: None
        """


        if self.host_os == 'windows':
            output_file = output_file.replace(r'/', '\\')
            path = path.replace('/', '\\')

        # Don't append path if we're currently dealing with a file in the root
        if path == '\\':
            output_path = self.output_dir + output_file
        else:
            output_path = self.output_dir + path + output_file

        # Make sure output director if it does not exists
        if not os.path.exists(os.path.dirname(output_path)):
            os.makedirs(os.path.dirname(output_path))

        try:
            with urllib.request.urlopen(download_url) as response, open(output_path.rstrip(), 'wb') as out_file:
                data = response.read()
                out_file.write(data)
        except urllib.error.HTTPError as e:
            print('ERROR: Failed to download: ', download_url)
            print('ERROR MSG: ' + e.msg)


        if self.verbose:
            print('Downloading File: ', output_file)

        if self.verbose:
            print('----- Thread Ending -----\n')


    def clear_screen(self):
        """
        Clear the screen.  Issue the correct command for OS running this script
        :return:
        """
        if self.host_os == 'windows':
            os.system('cls')
        elif self.host_os == 'posix':
            os.system('clear')


def main():
    parser = argparse.ArgumentParser(description="A wrapper for Windows Wget that will scan a whole http directory tree "
                                                 "and download all files. ")

    parser.add_argument("dl_url", help="This is the URL to download")
    parser.add_argument("--output", default=False, dest="output_dir")
    parser.add_argument("--threads", default=15, dest="threads", help="The number of download threads to run at once.")
    parser.add_argument("--verbose", action='store_true', help="Prints a more verbose output", default=False, dest="verbose")
    parser.add_argument("--mirror", action='store_true', help="Enable/Disable Wget's mirror functionality", default=False, dest="mirror")
    parser.add_argument("--no_parent", action="store_true", default=False, dest="no_parent")
    parser.add_argument("--no_host_directories", action="store_true", default=False, dest="no_host_directories")
    args = parser.parse_args()


    downloader = ThreadedWget(args.dl_url, args.output_dir, threads=args.threads,
                              verbose=args.verbose, mirror=args.mirror, no_parent=args.no_parent,
                              no_host_directories=args.no_host_directories)
    try:
        downloader.run()
    except KeyboardInterrupt:
        print('[!] Keyboard Quit Detected')

if __name__ == '__main__':
    main()