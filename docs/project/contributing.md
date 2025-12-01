# 💖 Contributing to Ushka: Join the Fun! 🐾

So, you're interested in contributing to Ushka? Fantastic! We're genuinely excited to build a strong, welcoming community around this project.

There are plenty of ways to help, from sprucing up the documentation and reporting pesky bugs to cooking up brilliant new features. Every little bit helps Ushka grow!

## 🐞 Found a Bug? Don't Keep it a Secret!

If you stumble upon a bug (they happen, even to the best of us), please open an issue on our [GitHub repository](https://github.com/kleber-code/ushka/issues). We promise not to make you feel bad.

To help us squash it quickly, please include:

*   A clear and descriptive title.
*   A detailed explanation of the bug, including steps to reproduce it (we're not mind readers, yet).
*   The versions of Ushka and Python you're using.
*   Any relevant code snippets or error messages.

## ✨ Got an Idea? Share Your Genius!

We're always open to new ideas for features. Feel free to open an issue to discuss your thoughts. We'd love to hear them!

## 🛠️ Setting Up for Development: It's Not Rocket Science!

Ready to get your hands dirty? Here’s how to set up your local development environment:

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
    This will set up a virtual environment and install all necessary dependencies, including development tools. Easy peasy.

3.  **Run Tests:**

    Before you start changing things, make sure everything's working as expected.

    ```bash
    pdm run pytest
    ```

4.  **Create a New Branch:**

    Branch off for your feature or bug fix. It keeps things tidy.

    ```bash
    git checkout -b my-awesome-feature
    ```

5.  **Make Your Changes:**

    Now, go forth and code!

## 🎁 Submitting Your Contribution: The Grand Finale!

Once you're satisfied with your changes, please submit a pull request to the `main` branch.

*   Ensure your code adheres to our existing style conventions (we like things neat).
*   If you've added a new feature, please include tests and update the documentation. We need to know what it does!
*   Write a clear and descriptive pull request message. Tell us all about your hard work.

We'll review your pull request as soon as we can. Thank you for making Ushka better! 💖
