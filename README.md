![NeoFab Logo](images/Logo_NeoFab.png)

# NeoFab - Multilingual 3D Print Order Management System

NeoFab is a Flask-based web application for managing 3D printing orders in labs, workshops, maker spaces, and research environments. It supports the full workflow from order submission and file upload to print job tracking, communication, documentation, and administrative review.

The application is built for multilingual use with English as the default language and German support through the included translation files.

## Features

- **User accounts and roles**  
  Registration, login, password reset, user profiles, admin users, disabled users, and deleted-user handling.

- **3D print order management**  
  Structured order data, project metadata, deadlines, approval information, cost centers, and status tracking.

- **Model and file handling**  
  Upload and manage 3D models, G-code files, and documentation attachments per order.

- **STL and 3MF viewer**  
  Browser-based model preview with reset, grid, axes, labels, wireframe mode, model information, and thumbnail support.

- **Print job tracking**  
  Create and manage print jobs with printer, material, color, print status, start time, and print parameters.

- **G-code metadata extraction**  
  G-code uploads can extract print duration, filament length, and filament weight from slicer comments. Missing values can also be filled later when opening an order.

- **Order list summaries**  
  Order lists show compact print job status badges for total jobs, jobs in progress, completed jobs, and failed jobs.

- **Integrated messaging**  
  Built-in communication between users and admins, persistent read status, and optional email notifications.

- **Admin area**  
  Manage users, materials, colors, printer profiles, cost centers, announcements, training playlists, training videos, logs, and orders.

- **Archiving and cleanup**  
  Admins can archive orders and permanently delete orders including database records and related files.

- **Audit and log support**  
  Logs include user activity, order changes, archive/delete operations, file cleanup details, and login timing diagnostics.

## Tech Stack

- Python 3
- Flask
- SQLAlchemy
- Flask-Login
- Werkzeug Security
- Bootstrap 5
- Jinja templates
- SQLite, MariaDB, or PostgreSQL
- Gunicorn and systemd for production deployments

## Project Structure

```text
neofab/
  app.py
  models.py
  notifications.py
  routes/
  static/
  templates/
  version.py
i18n/
  de.json
  en.json
  fr.json
doku/
  SETUP.md
  Version_Timeline.md
script/
  setupNeoFab
  setupNeoFabService
  upDateNeoFabService
  resetAdminPassword
images/
  Logo_NeoFab.png
  NeoFab_V0-8-6_*.jpg
```

## Setup

Installation and maintenance scripts are available in the `script/` directory.

Start with the setup documentation:

- [Script setup guide](script/README.md)
- [General setup notes](doku/SETUP.md)

The main scripts are:

- `script/setupNeoFab` - base installation and optional development server start
- `script/setupNeoFabService` - systemd service setup with Gunicorn
- `script/upDateNeoFabService` - update an existing service installation
- `script/resetAdminPassword` - emergency admin password reset

## Current Version

Current application version: **0.8.11**

Recent changes include documented 3D print cost calculation, order counts and linked order lists for cost centers, email notifications for announcements with priority "Achtung eMail", configurable email actions in the admin system settings, and improved order and print job overviews.

See [Version_Timeline.md](doku/Version_Timeline.md) for the detailed project history.

## Screenshots V0.8.6

### NeoFab Home

![NeoFab home](images/NeoFab_V0-8-6_-00.jpg)

### STL and 3MF Viewer

![STL and 3MF viewer](images/NeoFab_V0-8-6_-01.jpg)

### System Settings

![System settings](images/NeoFab_V0-8-6_-02.jpg)

### Admin Panel

![Admin panel](images/NeoFab_V0-8-6_-03.jpg)

### User Profile

![User profile](images/NeoFab_V0-8-6_-04.jpg)

### Communication and Chat

![Communication and chat](images/NeoFab_V0-8-6_-05.jpg)

### Order Print Jobs

![Order print jobs](images/NeoFab_V0-8-6_-06.jpg)

### Order 3D Models

![Order 3D models](images/NeoFab_V0-8-6_-07.jpg)

### Order Documentation

![Order documentation](images/NeoFab_V0-8-6_-08.jpg)

### Order Overview

![Order overview](images/NeoFab_V0-8-6_-09.jpg)

### Order List

![Order list](images/NeoFab_V0-8-6_-10.jpg)

### Login

![Login](images/NeoFab_V0-8-6_-11.jpg)

## License

See the included license files for licensing information.
