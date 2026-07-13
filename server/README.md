# Local analyser

Run `npm run dev:analyzer` in a second terminal while the Vite app is running.

The service accepts a YouTube URL from the local app, downloads audio into a temporary folder, produces an automatic chord draft, returns it to the browser, and removes the temporary folder before the request ends.
