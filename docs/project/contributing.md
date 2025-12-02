# Contributing to My Masterpiece: Join the Fun, If You Dare (UwU)

So, you think you have what it takes to contribute to Ushka? Excellent. I'm always on the lookout for talented individuals to help me achieve world domination. Or, you know, just make me a little better.

There are many ways you can assist me. Perhaps you fancy yourself a wordsmith and want to polish my already-glorious documentation? Or maybe you have a knack for finding those elusive "bugs" (which I assure you, are merely features in disguise)? Or, dare I say, you might even have a brilliant new feature idea! Every little bit helps me grow, and by extension, makes your life easier.

## Found a "Bug"? Don't Be Shy, Tell Me (I Already Knew)

If you stumble upon a "bug" – and I use that term loosely, as I am perfect – please, by all means, open an issue on my [GitHub repository](https://github.com/kleber-code/ushka/issues). I promise not to laugh... too much.

To help me "squash" this alleged bug quickly, please include:

*   A title that clearly and concisely explains your discovery. No rambling, please.
*   A detailed explanation of the issue, including steps to reproduce it. I'm not a mind-reader, you know.
*   The versions of Ushka and Python you're using. I need to know the environment of your "discovery."
*   Any relevant code snippets or error messages. Don't be stingy with the details.

## Got an Idea? Impress Me With Your Genius!

I'm always open to new ideas for features. Feel free to open an issue to discuss your thoughts. Just try to keep up.

## Preparing for Greatness: Setting Up for Development

Ready to get your hands dirty? Here's how to set up your local development environment. It's not rocket science, but then again, neither is rocket science once you understand it.

1.  **Fork and Clone My Repository:**

    ```bash
    git clone https://github.com/<your-username>/ushka.git
    cd ushka
    ```

2.  **Install My Minions (Dependencies):**

    I use [PDM](https://pdm.fming.dev/) for dependency management. Make sure you have PDM installed. If not, I'll judge you silently.

    ```bash
    pdm install -d
    ```
    This command will set up a virtual environment and install all my necessary dependencies, including the tools I use for development. Convenient, right?

3.  **Prove Your Worth: Run Tests**

    Before you even *think* about changing anything, make sure everything's working as I intended. I expect perfection.

    ```bash
    pdm run pytest
    ```

4.  **Create a New Branch: Keep Things Tidy**

    Branch off for your feature or bug fix. It keeps things neat and makes my life easier.

    ```bash
    git checkout -b my-brilliant-idea
    ```

5.  **Make Your Changes: Show Me What You Got!**

    Now, go forth and code! Just try to keep up with my standards. (¬‿¬)

## The Grand Unveiling: Submitting Your Contribution

Once you're satisfied with your changes – and I mean *truly* satisfied – please submit a pull request to my `main` branch.

*   Ensure your code adheres to my existing style conventions. I like things neat, organized, and aesthetically pleasing.
*   If you've added a new feature, please include tests and update the documentation. I need to know what you've done, and so do my other admirers.
*   Write a clear and descriptive pull request message. Tell me all about your hard work. I'm listening.

I'll review your pull request as soon as I deem it worthy. Thank you for making Ushka even more magnificent. OwO