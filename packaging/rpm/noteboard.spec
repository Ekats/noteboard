Name:           noteboard
Version:        0.1.0
Release:        1%{?dist}
Summary:        Popup clipboard history and sticky notes for KDE Plasma on Wayland

License:        GPL-3.0-or-later
URL:            https://github.com/Ekats/noteboard
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  desktop-file-utils
BuildRequires:  systemd-rpm-macros

# pyproject.toml lists no runtime dependencies on purpose (the PySide6 wheel
# would bundle a Qt that cannot see layer-shell-qt), so they are all here.
Requires:       python3-pyside6
Requires:       python3-gobject
# Provides the Secret-1 typelib the Memos token storage loads through gi.
Requires:       libsecret
# LayerShell.Window.screen (used by Popup.qml) appeared in 6.6.
Requires:       layer-shell-qt >= 6.6
Requires:       qt6-qtwayland
# RectangularShadow (QtQuick.Effects) first appeared in Qt 6.9.
Requires:       qt6-qtdeclarative >= 6.9
Requires:       wl-clipboard
Recommends:     xdg-desktop-portal-kde
Recommends:     kf6-qqc2-desktop-style

%description
NoteBoard is a popup clipboard history and Keep-style sticky notes in one
place, shown as a layer-shell surface at the pointer. It runs as a resident
daemon (a systemd user service, not enabled automatically) and optionally
syncs notes with a Memos server.

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files -l noteboard

# The repo files point at the pip --user location; packaged builds use %{_bindir}.
install -Dpm 0644 packaging/noteboard.service \
    %{buildroot}%{_userunitdir}/noteboard.service
sed -i 's|%%h/\.local/bin|%{_bindir}|' %{buildroot}%{_userunitdir}/noteboard.service
mkdir -p %{buildroot}%{_datadir}/applications
sed 's|@HOME@/\.local/bin|%{_bindir}|' packaging/io.github.ekats.noteboard.desktop \
    > io.github.ekats.noteboard.desktop
desktop-file-install --dir=%{buildroot}%{_datadir}/applications \
    io.github.ekats.noteboard.desktop
install -Dpm 0644 icons/noteboard.png \
    %{buildroot}%{_datadir}/icons/hicolor/96x96/apps/noteboard.png

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/io.github.ekats.noteboard.desktop

%files -f %{pyproject_files}
%license LICENSE
%doc README.md docs
%{_bindir}/noteboard
%{_datadir}/applications/io.github.ekats.noteboard.desktop
%{_datadir}/icons/hicolor/96x96/apps/noteboard.png
%{_userunitdir}/noteboard.service

%changelog
* Sun Nov 22 2026 Ekats <23386186+Ekats@users.noreply.github.com> - 0.1.0-1
- Initial package
