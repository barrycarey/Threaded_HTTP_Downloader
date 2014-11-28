import os
import sys
import argparse
import subprocess
import time
import threading
from bs4 import BeautifulSoup
import urllib.request
import urllib.error

# TODO Fix local last modifiec handling.  Currently using manual offset to adjusting Epoch time.  Remote file returns GMT Epoch, local files returns EST Epoch
# TODO Cleanup handling of slashes
# TODO Add a queue for files to download.  This way while waiting on max threads the download list can continue to build



"""
A class to parse a directory listing of a URL and spawn a Wget download for each file encountered.
The module uses Beautiful Soup to parse the URL and pull out all links.  The links are then checked
to determine of they are files or directories.  If it's a file a download thread is spawned.  If it's
a directory it crawls into it and repeats the process.

If on Windows script expects the Wget exe to be in the same directory or in util.

The module expects a raw directory listing of the URL. It will not work if there is a default HTML page at the URL.
"""
class ThreadedWget():

    def __init__(self, dl_url, output_dir, threads=15, mirror=False, verbose=False, debug=False):

        self.download_url = dl_url
        self.verbose = verbose
        self.threads = int(threads) # May not be needed. Check Argparse for getting int not str
        self.mirror = mirror
        self.debug = debug
        self.file_count = 0

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

    def run(self):
        """
        This method executes the actual download.  It calls the parse_remote_dir_tree method and waits for
        it to return.  Once it returns it waits until all download threads have finishes.  Prior to threads
        finishing it prints a list of the files currently being downloaded
        :return:
        """

        print('[+] Starting Parse And Download Of ' + self.download_url)
        if self.output_dir:
            print('[+] Output Directory is: ' + self.output_dir + '\n')

        self.parse_remote_dir_tree(self.download_url, '')

        print('\nAll Download Threads Launched.\n')
        # TODO Make thread checking it's own method
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

        self.clear_screen()
        print('[!] Success: ' + str(self.file_count) + ' Files Have Been Downloaded')
        time.sleep(5)
        self.clear_screen()

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

            if not link.string:
                self.clear_screen()
                print('[x] ERROR: No Links Found On Given URL')
                time.sleep(5)
                return

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
                print('[+] New Thread URL: ' + download_url)
                print('[+] New Thread File: ' + output_file)

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
            with urllib.request.urlopen(download_url) as response:

                # If mirror is enabled and file exists check if remote file is newer than local.
                if os.path.isfile(output_path) and self.mirror:
                    local_last_modified = self.get_local_timestamp(output_path)
                    remote_last_modified = self.get_remote_timestamp(response.info()['Last-Modified'])

                    # This func call may not be needed but may add more checks later
                    if self.mirror_compare_time(local_last_modified, remote_last_modified):
                        if self.verbose:
                            print('[+] MIRROR: Remote File Is Newer: ' + output_file)
                    else:
                        if self.verbose:
                            print('[+] MIRROR: Remote File Not Newer: ' + output_file)
                        return

                if self.debug:
                    print('[+]  Downloading File: ', output_file)

                out_file = open(output_path.rstrip(), 'wb')
                data = response.read()
                out_file.write(data)
                out_file.close()
                self.file_count += 1

        except urllib.error.HTTPError as e:
            print('[x] ERROR: Failed to download: ', download_url)
            print('[x] ERROR MSG: ' + e.msg)

        if self.verbose:
            print('[!] Thread Ending: ', output_file)

    def mirror_compare_time(self, local_file, remote_file):
        if self.debug:
            print('[?] Local File: ' + str(local_file))
            print('[?] Remote File: ' + str(remote_file))
        return True if remote_file > local_file else False

    def get_remote_timestamp(self, last_modified):
        """
        Convert the Last-Modified header time into epoch time
        :param last_modified: Last-Modified header timestamp
        :return: epoch time
        """
        if self.debug:
            print('[+] get_remote_timestamp called with: ' + last_modified)
        temp_time = time.strptime(last_modified, "%a, %d %b %Y %H:%M:%S %Z")
        #return time.mktime(time.strptime(last_modified, "%a, %d %b %Y %I:%M:%S %Z"))
        return round(time.mktime(temp_time))

    def get_local_timestamp(self, local_file):
        # TODO Sort out local timzone.  + 18000 is a temp fix for time difference
        return round(os.path.getmtime(local_file) + 18000)

    def clear_screen(self):
        """
        Clear the screen.  Issue the correct command for OS running this script
        :return:
        """
        if self.host_os == 'windows':
            os.system('cls')
        elif self.host_os == 'posix':
            os.system('clear')

        print('\n')


def main():
    parser = argparse.ArgumentParser(description="A wrapper for Windows Wget that will scan a whole http directory tree "
                                                 "and download all files. ")

    parser.add_argument("dl_url", help="This is the URL to download")
    parser.add_argument("--output", default=False, dest="output_dir")
    parser.add_argument("--threads", default=15, dest="threads", help="The number of download threads to run at once.")
    parser.add_argument("--verbose", action='store_true', help="Prints a more verbose output", default=False, dest="verbose")
    parser.add_argument("--mirror", action='store_true', help="Enable/Disable Wget's mirror functionality", default=False, dest="mirror")
    parser.add_argument("--debug", action="store_true", default=False, dest="debug", help="Print Debug Output")
    args = parser.parse_args()


    downloader = ThreadedWget(args.dl_url, args.output_dir, threads=args.threads, verbose=args.verbose,
                              mirror=args.mirror, debug=args.debug)
    try:
        downloader.run()
    except KeyboardInterrupt:
        print('[!] Keyboard Quit Detected')

if __name__ == '__main__':
    main()