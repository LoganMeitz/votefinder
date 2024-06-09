# Installation and Setup

**Note:** There are, of course, many different ways to get a Django project accessible to the world on a server. Feel free to do this however you'd like - this guide is primarily for setting up Votefinder itself. 

## Clone Votefinder

Use `git clone` to download the Votefinder project into whatever directory you want it to live in on your server.

## Virtual Environment Setup

Make sure the virtualenv package is installed, create a new virtual environment, then activate it.

```bash
pip install virtualenv
virtualenv /var/venvs/venv
source /var/venvs/venv/bin/activate
```

The virtual environment can be installed wherever you'd like; just make sure you know where it is.

If you'd like to keep your Votefinder venv alongside the Votefinder code, the `.gitignore` for this repo already has an entry for `/vfvenv`.

Install the requirements from `requirements.txt` into the virtual environment.

```bash
cd votefinder
pip install -r requirements.txt
```

## Configure Your .env File And Database

The `.env.sample` file is a .env file where you can input things like your database hostname and password. Rename it to `.env` and uncomment the required settings and/or provide them values.

The settings `VF_MYSQL_HOST`, `VF_MYSQL_USER`, `VF_MYSQL_PASS` and `VF_MYSQL_NAME` are the hostname, user, password and name of the database that Votefinder will use. If your MySQL server doesn't already have a database with that name, create it first. Then, run `python manage.py migrate` to get all the necessary tables created - the database should need no other changes to be made manually by an administrator.

`VF_DOMAINS` is a list of domain names Votefinder can be accessed from.

There must be a player with uid of -1 present in your database.
