Gmail unread-attachment printer.

SETUP
-----
1. Enable the Gmail API in Google Cloud and create an OAuth client of type
   "Desktop app". Download the client JSON as ``credentials.json`` beside
   this file.
2. Install Python 3.10+ and the dependencies:

   python -m pip install google-api-python-client google-auth-oauthlib google-auth

3. Run:

   python gmail_attachment_printer.py

The first run opens Google's OAuth consent flow. ``token.json`` and
``settings.json`` are created beside this script. Keep both files private.

Printing notes
--------------
Windows uses the default shell application's ``print`` verb. macOS and Linux
use the standard ``lp`` command. On Windows, the shell print verb returns once
the document has been handed to the registered print application; on macOS
and Linux, a successful ``lp`` exit means the job was accepted by CUPS.
The default application must support the selected file type.