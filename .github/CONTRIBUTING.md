# 💖 Contributing to Ushka: A Little Love Goes a Long Way! 🎀

(Or: How to Help Us Make Python Even Cuter, Without Breaking Everything)

Thank you for even *thinking* about contributing to Ushka! We're thrilled to have you. Whether it's a tiny typo fix, a brilliant new feature idea, or a serious bug report, your help makes Ushka grow into the framework of our (and hopefully your) dreams.

---

## 🚧 A Note on Our Current State (Transparency is Cute!)

Ushka is still a spirited toddler (in **Alpha** stage!), and while we adore contributions, please remember this project is currently maintained by a single, very caffeinated human. That means review times might be a tad slow. Don't let this discourage you – your input is invaluable!

---

## 💡 How Can You Help? (So Many Ways to Be Awesome!)

There are many ways to lend a paw to Ushka:

### 🐛 Reporting Bugs: Found a Critter? Squish It (Virtually)!

If you find something that doesn't quite work as expected, please open an issue on our [GitHub repository](https://github.com/kleber-code/ushka/issues). Include:

*   A clear, concise title (no riddles, please).
*   Detailed steps to reproduce the bug (we need to see it to fix it!).
*   The version of Ushka and Python you're using.
*   Any relevant code snippets or error messages. (Screenshots of "Ushka Panic!" are particularly helpful!)

### ✨ Suggesting Features: Dream Big, Little One!

Got a brilliant idea that would make Ushka even better? Head over to our [issue tracker](https://github.com/kleber-code/ushka/issues) and open a feature request. Tell us:

*   What problem does this feature solve?
*   How would it work from a user's perspective?
*   Why do you think it fits Ushka's minimalist, cute philosophy?

### 📝 Improving Documentation: Words of Wisdom!

Is something unclear? A typo lurking? Or do you just have a knack for explaining complex things with charming simplicity? Contributions to our documentation are *always* welcome. A pull request is the perfect way to suggest changes.

### 🧑‍💻 Code Contributions: Let's Get Coding!

If you're looking to dive into the codebase, that's amazing! Here’s a quick guide:

1.  **Read the Code of Conduct:** Please, it's important. (`.github/CODE_OF_CONDUCT.md`)
2.  **Check the Roadmap:** See what we're planning in `docs/project/roadmap.md` to avoid duplicate work.
3.  **Setup Your Environment:** Follow the "Development Setup" in `docs/guide/contributing.md` (oops, this is that file! See section below.)
4.  **Create a Branch:** `git checkout -b my-awesome-contribution`
5.  **Code Away:** Make your changes, add tests, and update documentation if necessary.
6.  **Submit a Pull Request:** More details below!

---

## 🛠️ Development Setup: Get Your Paws Ready!

To get your local Ushka development environment purring, follow these steps:

1.  **Fork & Clone:** Grab your own copy of Ushka.
    ```bash
    git clone https://github.com/<your-username>/ushka.git
    cd ushka
    ```
2.  **Install PDM:** We use [PDM](https://pdm.fming.dev/) for dependency management. Make sure it's installed globally.
3.  **Install Dependencies:**
    ```bash
    pdm install -d # This installs dev dependencies too!
    ```
4.  **Run Tests:** Keep Ushka healthy!
    ```bash
    pdm run pytest
    ```

---

## 🚀 Submitting a Pull Request: The Grand Unveiling!

When your contribution is ready for the world, send us a pull request to the `main` branch!

*   **One Thing at a Time:** Keep your PR focused on a single feature or bug fix.
*   **Clear Description:** Tell us what your PR does, why it's needed, and how we can test it. Screenshots for UI/DX changes are a bonus!
*   **Tests & Docs:** If you add new code, please add tests. If it changes behavior or adds functionality, update the docs.
*   **Code Style:** We use Black and Ruff. `pdm run ruff check --fix && pdm run ruff format` will make Ushka happy.
*   **Be Patient (Again!):** We'll review it as soon as we can. We appreciate you!

Thank you for helping us make Ushka the best (and cutest!) Python web framework out there! 💖
