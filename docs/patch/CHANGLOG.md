# Changelog

## [Unreleased]

### Added
- Added upstream URL and service name to `Tasks` page
- Added pagination filter tasks in Backend API (`TasksDataTable` class)
- Added Expired columns to `Tasks` page for detect which task is expired
- Added to logic to cache data task for prevent `upstream` and `service` value is None when task is expired or deleted in Redis

### Fixed
- Fixed filter task state display logic
- Fixed task display when task in STARTED state
- Fixed task display when task in PENDING state


