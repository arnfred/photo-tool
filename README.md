Utils for uploading albums to my photo gallery. This code is oooold.

# Local Dev

## Photo-tools web util

To run the photo-tools webserver locally, use:

```
make run-prod
```

Now you can access the server in your browser on `http://localhost:8000`. The `--timeout` is added to make sure gunicorn is patient and waits for the photo upload to complete before shutting down threads.

## Login Details

See `aws.prod.env` or `aws.test.env` for login details under `SIMPLELOGIN_USERNAME` and `SIMPLELOGIN_PASSWORD`. If you for whatever reason need to change these, you'll need to manually ssh on to `dynkarken.com` and update the environment with the new values:

```
ssh dynkarken.com
dokku config:set photo-tools SIMPLELOGIN_USERNAME=<user> SIMPLELOGIN_PASSWORD=<pass>
```

## Deploying to dokku

To deploy to dokku, push to the git origin `dynkarken`

## Photo-tools cli

To use the command line tool, use:

```
# Create new album configuration file
./photos.py init -n <album name> [-p <conf path> -f <conf name>]

# Upload new version of gallery configuration file
./photos.py gallery -u [-p <gallery conf path>] 

# Convert old conf format to toml
./photos.py convert [-d <conf directory> -s <conf files to skip separated by ,> -q <enable dry-run>] 

# Publish albums
./photos.py publish -d <conf directory> [-w <upload images> -t <temp dir> -s <conf files to skip> -k <Keep temp dir>]
```

# Setting up Dokku

I'm adding a bit of info on setting up new services on my host here, since I don't have any information on that anywhere else.

To set up a new service, use this guide: http://dokku.viewdocs.io/dokku/deployment/application-deployment/

```
ssh dynkarken.com
dokku apps:create photo-tools
```

Then locally, add dynkarken as a git remote:

```
git remote add dynkarken dokku@dynkarken.com:photo-tools
```

Next to set up the environment for the app, copy the local env file and ssh onto dynkarken.com, then set the config for the app:

```
dokku config:set photo-tools <ENV key value pairs with = between>
```

To set up the domain, we use the instructions here: http://dokku.viewdocs.io/dokku/configuration/domains/

```
dokku domains:add photo-tools blah.ifany.org
```

# Adding ffmpeg to server

To use the ffmpeg binary from the python app, I've added a ffmpeg buildpack in the `.buildpacks` file
