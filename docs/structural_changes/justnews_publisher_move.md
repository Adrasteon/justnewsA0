# JustNews Publisher Structural Change

## Overview

This document explains the structural change involving the move of the `justnews_publisher` directory from the `agents/publisher/` folder to the root folder of the JustNews project.

## Background

The `justnews_publisher` was initially located in the `agents/publisher/` folder, reflecting its role as an agent within the JustNews system. However, as the project evolved, it became clear that the `justnews_publisher` is not truly an agent but a full Django-based website publishing system used to publish the output from the rest of the JustNews system.

## Reasons for the Move

1. **Clarity**: Moving the `justnews_publisher` to the root folder better reflects its role and importance within the project. It is not just another agent but a critical component of the publishing workflow.

2. **Functionality**: The `justnews_publisher` is designed to be a full Django-based website publishing system, which includes its own settings, URLs, and WSGI/ASGI configurations. Placing it in the root folder makes it easier to manage and integrate with other parts of the system.

3. **Consistency**: The move aligns with the project's goal of having a clear and consistent structure, where major components are easily identifiable and accessible.

## Changes Made

1. **Directory Structure**: The `justnews_publisher` directory has been moved from `agents/publisher/justnews_publisher/` to the root folder as `justnews_publisher/`.

2. **Path Updates**: All references to the old path (`agents/publisher/justnews_publisher/`) have been updated to reflect the new path (`justnews_publisher/`).

3. **Configuration Updates**: The `settings.py` file in the `justnews_publisher/` directory has been updated to include comprehensive configurations, including observability setup and additional imports.

4. **Workflow Updates**: The GitHub Actions workflow file (`.github/workflows/editorial-harness-publish-sandbox.yml`) has been updated to reflect the new path for the `justnews_publisher`.

5. **Integration Updates**: The `agents/common/publisher_integration.py` file has been updated to reflect the new path for the publisher's SQLite database.

## Impact

- **Development**: Developers should be aware of the new location of the `justnews_publisher` directory and update any local configurations or scripts accordingly.

- **Deployment**: Deployment scripts and configurations should be reviewed to ensure they reflect the new path for the `justnews_publisher`.

- **Documentation**: This document serves as a reference for the structural change and should be consulted when working with the `justnews_publisher` component.

## Future Considerations

- **Testing**: Ensure that all tests and integration points are updated to reflect the new path for the `justnews_publisher`.

- **Documentation**: Update any additional documentation or guides that reference the old path for the `justnews_publisher`.

- **Communication**: Communicate the change to all team members and stakeholders to ensure a smooth transition.

## Conclusion

The move of the `justnews_publisher` directory to the root folder is a significant structural change that reflects its evolved role within the JustNews project. This change improves clarity, functionality, and consistency, making it easier to manage and integrate the publishing system with other parts of the project.
