# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
Name:           speedtester
Version:        %{?version}%{!?version:0.3.0}
Release:        1%{?dist}
Summary:        SpeedTester broadband measurement client
License:        GPL-3.0-or-later
URL:            https://github.com/ecarara/SpeedTester
Requires:       python3 >= 3.11
Requires:       iperf3
BuildArch:      %{_arch}
Source0:        speedtester-%{version}.tar.gz

%description
SpeedTester schedules broadband measurements, persists results and provides a
local dashboard. The package installs a user-level launcher and services.

%prep
%setup -q

%install
mkdir -p %{buildroot}/usr/lib/speedtester
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/lib/systemd/user
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
cp -a app %{buildroot}/usr/lib/speedtester/app
cp -a venv %{buildroot}/usr/lib/speedtester/venv
install -m 0755 speedtester-launcher %{buildroot}/usr/bin/speedtester-launcher
install -m 0644 speedtester.desktop %{buildroot}/usr/share/applications/speedtester.desktop
install -m 0644 speedtester-api.service %{buildroot}/usr/lib/systemd/user/speedtester-api.service
install -m 0644 speedtester-client.service %{buildroot}/usr/lib/systemd/user/speedtester-client.service
install -m 0644 speedtester.png %{buildroot}/usr/share/icons/hicolor/512x512/apps/speedtester.png
install -m 0644 LICENSE %{buildroot}/usr/lib/speedtester/LICENSE

%files
%license /usr/lib/speedtester/LICENSE
/usr/bin/speedtester-launcher
/usr/lib/speedtester
/usr/lib/systemd/user/speedtester-api.service
/usr/lib/systemd/user/speedtester-client.service
/usr/share/applications/speedtester.desktop
/usr/share/icons/hicolor/512x512/apps/speedtester.png

%postun
systemctl --user daemon-reload >/dev/null 2>&1 || :
