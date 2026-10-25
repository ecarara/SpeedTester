# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
Name:           speedtester
Version:        %{?version}%{!?version:0.3.0}
Release:        1%{?dist}
Summary:        SpeedTester broadband measurement client
License:        GPL-3.0-or-later
URL:            https://github.com/ecarara/SpeedTester
Requires:       iperf3
Requires:       xdg-utils
BuildArch:      %{_arch}
Source0:        speedtester-%{version}.tar.gz

# Prebuilt PyInstaller executables contain an appended Python archive. Stripping
# or generating debuginfo can discard it; source files are retained for review,
# not byte-compiled using a packaging host's unrelated Python installation.
%global debug_package %{nil}
%global __strip /bin/true
%global __brp_python_bytecompile %{nil}

%description
SpeedTester schedules broadband measurements, persists results and provides a
local dashboard. The package installs a user-level launcher and services.

%prep
%setup -q

%install
mkdir -p %{buildroot}/usr/lib/speedtester
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/speedtester
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/lib/systemd/user
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
cp -a app %{buildroot}/usr/lib/speedtester/app
cp -a runtime %{buildroot}/usr/lib/speedtester/runtime
install -m 0755 speedtester-launcher %{buildroot}/usr/bin/speedtester-launcher
install -m 0755 configure-user.sh %{buildroot}/usr/lib/speedtester/configure-user.sh
install -m 0644 speedtester.env.example %{buildroot}/usr/share/speedtester/speedtester.env.example
install -m 0644 speedtester.desktop %{buildroot}/usr/share/applications/speedtester.desktop
install -m 0644 speedtester-api.service %{buildroot}/usr/lib/systemd/user/speedtester-api.service
install -m 0644 speedtester-client.service %{buildroot}/usr/lib/systemd/user/speedtester-client.service
install -m 0644 speedtester.png %{buildroot}/usr/share/icons/hicolor/512x512/apps/speedtester.png
install -m 0644 LICENSE %{buildroot}/usr/lib/speedtester/LICENSE

%files
%license /usr/lib/speedtester/LICENSE
/usr/bin/speedtester-launcher
/usr/lib/speedtester
/usr/share/speedtester/speedtester.env.example
/usr/lib/systemd/user/speedtester-api.service
/usr/lib/systemd/user/speedtester-client.service
/usr/share/applications/speedtester.desktop
/usr/share/icons/hicolor/512x512/apps/speedtester.png

%post
if command -v runuser >/dev/null 2>&1 && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ] && [ -x /usr/lib/speedtester/configure-user.sh ]; then
    runuser -u "$SUDO_USER" -- env \
        SPEEDTESTER_CONFIRM_EXISTING=1 \
        SPEEDTESTER_ENV_TEMPLATE=/usr/share/speedtester/speedtester.env.example \
        /usr/lib/speedtester/configure-user.sh || :
fi
if command -v runuser >/dev/null 2>&1 && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != root ]; then
    runuser -u "$SUDO_USER" -- systemctl --user daemon-reload >/dev/null 2>&1 || :
    runuser -u "$SUDO_USER" -- systemctl --user try-restart speedtester-api.service speedtester-client.service >/dev/null 2>&1 || :
fi

%postun
systemctl --user daemon-reload >/dev/null 2>&1 || :
