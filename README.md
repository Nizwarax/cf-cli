# Cloudflare Manager CLI

This is a simple command-line tool for managing your Cloudflare accounts.

## Installation

Run the following command in your terminal to download and run the installer:

```bash
curl -sSL https://raw.githubusercontent.com/Nizwarax/cf-cli/main/install.sh | bash
```
## Usage

Once the installation is complete, you can run the script by typing `cf` in your terminal:

```bash
cf
```


## Configuration: Creating a Cloudflare API Token

Before using the script, you need to create a Cloudflare API Token with the correct permissions.

1.  **Log in** to your Cloudflare dashboard.
2.  Go to **My Profile** > **API Tokens**.
3.  Click **Create Token**, then select **Create Custom Token**.
4.  Give your token a descriptive name (e.g., "Manager CLI Script").
5.  Set the following permissions:
    *   `Zone` - `Zone` - `Read`
    *   `Zone` - `Zone` - `Edit`
    *   `Zone` - `DNS` - `Read`
    *   `Zone` - `DNS` - `Edit`
6.  Click **Continue to summary**, then **Create Token**.
7.  **Copy the generated token immediately.** You will not be able to see it again.

Once you have the token, run the script and use the "Add New Account" option to add it.

## Usage

Once the installation is complete, you can run the script by typing `cf` in your terminal:

```bash
cf
```
