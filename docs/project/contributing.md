# Contributing

Thank you for your interest in contributing to Ushka! We are excited to build a strong community around this project.

There are many ways to contribute, from writing documentation and reporting bugs to submitting new features.

## Reporting Bugs

If you find a bug, please open an issue on our [GitHub repository](https://github.com/kleber-code/ushka/issues).

Please include the following in your bug report:

-   A clear and descriptive title.
-   A detailed description of the bug, including the steps to reproduce it.
-   The version of Ushka and Python you are using.
-   Any relevant code snippets or error messages.

## Suggesting Features

We welcome suggestions for new features. Feel free to open an issue to discuss your ideas. We want to hear from you!

## Development Setup

To get started with local development, follow these steps:

1.  **Fork and Clone the Repository:**

    ```bash
    git clone https://github.com/<your-username>/ushka.git
    cd ushka
    ```

2.  **Install Dependencies:**

    Ushka uses [PDM](https://pdm.fming.dev/) for dependency management. Make sure you have PDM installed.

    ```bash
    pdm install -d
    ```
    This will create a virtual environment and install all the necessary dependencies, including development tools.

3.  **Run Tests:**

    Before you start making changes, make sure all tests are passing.

    ```bash
    pdm run pytest
    ```

4.  **Create a New Branch:**

    Create a new branch for your feature or bug fix.

    ```bash
    git checkout -b my-awesome-feature
    ```

5.  **Make Your Changes:**

    Now you can start making your changes to the codebase.

## Submitting a Pull Request

Once you are happy with your changes, please submit a pull request to the `main` branch.

-   Make sure your code follows the existing style conventions.
-   If you are adding a new feature, please include tests and documentation.
-   Write a clear and descriptive pull request message.

We will review your pull request as soon as possible. Thank you for your contribution!
