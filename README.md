# OCI Free Tier Capacity Hunter

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![OCI](https://img.shields.io/badge/Oracle%20Cloud-Always%20Free-red.svg)

A Python script that automatically retries claiming an **Oracle Cloud Infrastructure (OCI) Always Free** **Ampere A1** (ARM) instance via a Resource Manager Stack, for whenever you hit the classic *"Out of host capacity"* error during free tier signup.

> ⚠️ **Disclaimer:** This automates repeated API calls against your own OCI tenancy to work around temporary capacity shortages. It is **not officially endorsed by Oracle**, and aggressive/long-running automated polling can be flagged by Oracle's abuse-detection systems, potentially leading to account review or suspension. Use reasonable polling intervals (see Configuration below), monitor your account, and use this entirely at your own risk.

---

## What you need before starting

1. An Oracle Cloud account (Free Tier is fine).
2. A Resource Manager **Stack** already created in your tenancy, configured to provision the Ampere A1 instance you want (this script does not create the stack — it only repeatedly *applies* an existing one).
   - When you walk through the **Create Stack** wizard (whether you use Oracle's official Always Free ARM template or your own Terraform), it asks for an **SSH public key** as part of the instance configuration — this gets baked into the stack's variables (`ssh_authorized_keys` or similar) and is what gets injected into the VM's `~/.ssh/authorized_keys` on first boot.
   - This script never touches SSH keys itself — it only calls `create_job` (APPLY) against the stack you already configured, so whatever public key you set during stack creation is exactly what will be on the instance once a job finally `SUCCEEDED`s.
   - Keep the matching **private key** safe — that's what you'll use to SSH into the instance afterward (e.g. `ssh -i /path/to/private_key ubuntu@<instance-public-ip>`). This is a separate, unrelated key pair from `oci_private_key.pem`, which is only used for OCI API authentication.
3. Python 3.8+ installed.

---

## Step 1: Get your OCI credentials

You need 5 pieces of information from the OCI Console. All of them are safe to view — none of them are secret by themselves except the private key file.

### 1. User OCID
- Log in to the [OCI Console](https://cloud.oracle.com).
- Click the **Profile icon** (top right) → **User Settings**.
- Copy the **OCID** shown under your username (starts with `ocid1.user.oc1..`).

### 2. Tenancy OCID
- Click the **Profile icon** → **Tenancy: <your-tenancy-name>**.
- Copy the **OCID** shown (starts with `ocid1.tenancy.oc1..`).

### 3. API Signing Key + Fingerprint
- Go to **Profile icon** → **User Settings**.
- Scroll to **API Keys** → click **Add API Key**.
- Choose **Generate API Key Pair**.
- Click **Download Private Key** — this downloads a `.pem` file. **This is the only secret file.**
- Click **Add** to register the key. OCI will now show you a **Fingerprint** (looks like `15:52:75:9b:53:ca:...`) — copy it.
- Rename the downloaded private key file to `oci_private_key.pem` and place it in the same folder as the script.

### 4. Region
- The short region code is shown in the top-right region dropdown, e.g. `ap-mumbai-1` for India South (Mumbai).

### 5. Resource Manager Stack OCID
- Go to **Developer Services** → **Resource Manager** → **Stacks**.
- Click on the stack you want this script to apply.
- Copy the **OCID** from the stack's details page (starts with `ocid1.ormstack.oc1...`).

---

## Step 2: Set up the project

```bash
# Clone the repo
git clone https://github.com/MaheshTechnicals/oci-free-tier-capacity-hunter.git
cd oci-free-tier-capacity-hunter

# (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate   # on Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Place your downloaded private key file (renamed to `oci_private_key.pem`) in the project folder.

---

## Step 3: Configure your credentials

```bash
cp .env.example .env
```

Open `.env` in any text editor and fill in the 5 values you collected in Step 1:

```env
OCI_USER_OCID=ocid1.user.oc1..your-value-here
OCI_FINGERPRINT=15:52:75:9b:53:ca:8f:5e:92:cd:af:b4:1b:3f:9f:00
OCI_KEY_FILE=./oci_private_key.pem
OCI_TENANCY_OCID=ocid1.tenancy.oc1..your-value-here
OCI_REGION=ap-mumbai-1
OCI_STACK_ID=ocid1.ormstack.oc1.ap-mumbai-1.your-value-here
```

**Important:** `.env` and `*.pem` are already listed in `.gitignore` — never remove them from there, and never commit your real `.env` or private key file to GitHub.

---

## Step 4: Run the script

```bash
python oci_capacity_hunter.py
```

The script will keep retrying with randomized delays until it successfully claims capacity, then exit automatically. You can stop it anytime with `Ctrl+C` and resume later by running it again.

---

## Configuration (optional)

These can be tuned in your `.env` file. Defaults are already set conservatively — don't go lower than these unless you understand the tradeoff.

| Variable | Default | Meaning |
|---|---|---|
| `MIN_WAIT` / `MAX_WAIT` | 90 / 240 | Random delay range (seconds) between retry attempts |
| `RATE_LIMIT_BASE` / `RATE_LIMIT_MAX` | 60 / 600 | Backoff range when hitting OCI's 429 rate limit |
| `COOLDOWN_EVERY` | 15 | After this many consecutive failed attempts... |
| `COOLDOWN_MINUTES` | 20 | ...pause for this long before resuming |

Lowering `MIN_WAIT`/`MAX_WAIT` to hammer the API faster increases the chance of being flagged for abuse — this is not just a courtesy setting, it's a real risk to your account.

---

## Troubleshooting

- **`Missing required environment variables`** → You haven't created `.env` from `.env.example`, or left a field blank.
- **`Private key file not found`** → Check the `OCI_KEY_FILE` path in `.env` matches where you placed the `.pem` file.
- **401/403 errors** → Usually a wrong OCID, fingerprint, or key mismatch. The script will stop immediately rather than retry, since retrying auth failures looks like credential-stuffing to Oracle's systems. Double check Step 1.
- **Stuck at 429s repeatedly** → You're polling too fast or too many other things are using the API key simultaneously. Increase `MIN_WAIT`/`MAX_WAIT`.

---

## License

MIT — use, modify, and share freely. No warranty; see Disclaimer above.
