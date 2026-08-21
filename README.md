# v2rayN-oldos

### The same v2rayN, still running on the operating systems upstream dropped

[![Release](https://img.shields.io/github/v/release/aleksandr-miheichev/v2rayN-oldos?logo=github&label=Release)](https://github.com/aleksandr-miheichev/v2rayN-oldos/releases)
[![Downloads](https://img.shields.io/github/downloads/aleksandr-miheichev/v2rayN-oldos/total?logo=github&label=Downloads)](https://github.com/aleksandr-miheichev/v2rayN-oldos/releases)
[![Upstream](https://img.shields.io/badge/upstream-2dust%2Fv2rayN-blue?logo=github)](https://github.com/2dust/v2rayN)
[![License](https://img.shields.io/badge/license-GPL--3.0-green)](LICENSE)

This is an unofficial build of [2dust/v2rayN](https://github.com/2dust/v2rayN). The application is upstream's,
unchanged in behaviour; the difference is that these builds keep working on systems upstream no longer supports.

| | Supported here |
| --- | --- |
| Ubuntu | 22.04 and newer |
| Debian | 12 and newer |
| RHEL, Rocky, AlmaLinux | 9 and newer |
| macOS | 13.6 and newer |
| Windows | 10 and newer, x64 and arm64 |

**Why this exists.** Upstream releases from 7.23.2 onwards stopped installing on Ubuntu 22.04, Debian 12 and
RHEL 9. Two independent causes: the native SQLite library began requiring `GLIBC_2.38` and the relative
relocations ABI tag, and the package metadata began demanding `glibc >= 2.39`. Upstream
[declined](https://github.com/2dust/v2rayN/pull/9832) to keep supporting older systems. This fork restores both:
it uses a SQLite build with a `GLIBC_2.34` baseline and declares dependency floors those distributions can meet.

**How it is kept current.** Every upstream commit is pulled in automatically and a release is published without
waiting for upstream to cut one. No release is published unless its packages have been installed and the
application has been started on Ubuntu 22.04, Debian 12 and Rocky Linux 9, unless every shipped binary stays
within the `GLIBC_2.34` baseline, and unless the macOS application launches and its native libraries load on
macOS 14 and 15 with no shipped binary demanding a newer macOS than 13.6. Release notes are generated from the
commits that actually landed, and list changes that produced no commit at all — a dependency resolving to a new
version, a rebuilt native library. A failed release files an issue against this repository by itself, with the
failing job's own error messages in the body.

**Installing.**

```bash
# Ubuntu / Debian
sudo apt install ./v2rayN-linux-64.deb
# RHEL / Rocky / AlmaLinux
sudo dnf install ./v2rayN-linux-rhel-64.rpm
```

On macOS, open the `.dmg` and drag the application to Applications; the build is not notarized, so on first
launch either right-click → Open, or clear the quarantine flag: `xattr -rd com.apple.quarantine /Applications/v2rayN.app`.
On Windows, unpack the zip anywhere and run `v2rayN.exe`.

**What is not built here.** LoongArch and RISC-V packages. Everything else upstream publishes is published here.

**Verifying a download.** Each file has a `.sig` beside it, and every release includes `v2rayN-public-key.asc`:

```bash
gpg --import v2rayN-public-key.asc
gpg --verify v2rayN-linux-64.deb.sig v2rayN-linux-64.deb
```

Bugs in the application itself belong [upstream](https://github.com/2dust/v2rayN/issues). Use this repository's
issues for problems with these builds: packaging, compatibility with older systems, releases and signatures.

---

# v2rayN

### A GUI client for Windows, Linux and macOS. Support [Xray](https://github.com/XTLS/Xray-core) and [sing-box](https://github.com/SagerNet/sing-box) and [others](https://github.com/2dust/v2rayN/wiki/List-of-supported-cores)

[![CodeFactor](https://www.codefactor.io/repository/github/2dust/v2rayn/badge)](https://www.codefactor.io/repository/github/2dust/v2rayn)
[![Release](https://img.shields.io/github/v/release/2dust/v2rayN?logo=github&label=Release)](https://github.com/2dust/v2rayN/releases)
[![Downloads](https://img.shields.io/github/downloads/2dust/v2rayN/latest/total?logo=github&label=Downloads)](https://github.com/2dust/v2rayN/releases)
[![Telegram](https://img.shields.io/badge/Telegram-Chat-26A5E4?logo=telegram)](https://t.me/v2rayn)
 
[![Windows](https://img.shields.io/badge/Windows-supported-0078D6?logo=windows)](https://github.com/2dust/v2rayN) 
[![Linux](https://img.shields.io/badge/Linux-supported-FCC624?logo=linux&logoColor=000)](https://github.com/2dust/v2rayN) 
[![macOS](https://img.shields.io/badge/macOS-supported-000000?logo=apple)](https://github.com/2dust/v2rayN) 
[![GPG Signed](https://img.shields.io/badge/GPG-signed-4B32C3?logo=gnuprivacyguard)](https://github.com/2dust/v2rayN)


---

## Download / 下载

Download the latest release here:

在这里下载最新版本：

[https://github.com/2dust/v2rayN/releases](https://github.com/2dust/v2rayN/releases)


> [!TIP]
> v2rayN is the desktop version. For the mobile version, please visit the v2rayNG \
> v2rayN 是电脑版，手机版请访问 v2rayNG
>
> https://github.com/2dust/v2rayNG

---

## Documentation / 使用文档

Read the Wiki for usage guides and configuration details.

请阅读 Wiki 获取使用说明和配置教程。

[https://github.com/2dust/v2rayN/wiki](https://github.com/2dust/v2rayN/wiki)

---

## Supported Platforms / 支持平台

| Platform / 平台 | x64 | x86 | arm64 | riscv64 | loong64 |
| --- | --- | --- | --- | --- | --- |
| Windows | ✅ | ✅ | ✅ | - | - |
| Linux | ✅ | - | ✅ | ✅ | ✅ |
| macOS | ✅ | - | ✅ | - | - |

Minimum OS requirements: [Release files introduction](https://github.com/2dust/v2rayN/wiki/Release-files-introduction) / 最低系统要求：[发布文件介绍](https://github.com/2dust/v2rayN/wiki/Release-files-introduction)

---

## GPG Verification / GPG 签名校验

Release files are signed with GPG to verify authenticity and integrity, helping prevent mirror, ISP, or CDN hijacking.

发布文件已使用 GPG 签名，可用于校验文件真实性与完整性，预防镜像站、运营商或 CDN 劫持。

### Fingerprint / 公钥指纹

```text
7694 5E9F 3E9A 168F 8070 F195 805D 661C
134D FAF6 8903 C199 463C 31E5 AE90 3AE0
```

---

## Community / 社区

Telegram Group / Telegram 群组：

[https://t.me/v2rayN](https://t.me/v2rayN)

Telegram Channel / Telegram 频道：

[https://t.me/github_2dust](https://t.me/github_2dust)

<!-- probe -->
