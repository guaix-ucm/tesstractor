# Built in https://copr.fedorainfracloud.org/coprs/sergiopr/tesstractor/
# by Packit for each GitHub release (.packit.yaml), Version is set from the tag
Name:           tesstractor
Version:        0.8.0
Release:        1%{?dist}
Summary:        Read data from TESS and SQM-LU sky brightness photometers

License:        GPL-3.0-or-later
URL:            https://github.com/guaix-ucm/tesstractor
Source:         %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  systemd-rpm-macros

%description
Tesstractor reads data from TESS and Unihedron SQM-LU sky brightness
photometers, and writes it to daily files in the IDA format (NSBM
standard) and to MQTT servers.


%prep
%autosetup -p1 -n %{name}-%{version}


%generate_buildrequires
# setuptools_scm can not get the version from a tarball
export SETUPTOOLS_SCM_PRETEND_VERSION=%{version}
%pyproject_buildrequires -x test


%build
export SETUPTOOLS_SCM_PRETEND_VERSION=%{version}
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files -l tesstractor
install -Dpm 0644 extras/tesstractor.service %{buildroot}%{_unitdir}/tesstractor.service
install -Dpm 0644 extras/tesstractor-plot.service %{buildroot}%{_unitdir}/tesstractor-plot.service
install -Dpm 0644 extras/tesstractor-plot.timer %{buildroot}%{_unitdir}/tesstractor-plot.timer
# The configuration may contain the MQTT password
install -Dpm 0600 src/tesstractor/base.ini %{buildroot}%{_sysconfdir}/tesstractor/config.ini
install -dm 0755 %{buildroot}%{_sharedstatedir}/tesstractor


%check
%pytest -o asyncio_mode=auto --pyargs tesstractor


%post
%systemd_post tesstractor.service tesstractor-plot.timer

%preun
%systemd_preun tesstractor.service tesstractor-plot.service tesstractor-plot.timer

%postun
%systemd_postun_with_restart tesstractor.service
%systemd_postun tesstractor-plot.service tesstractor-plot.timer


%files -f %{pyproject_files}
%doc README.md
%{_bindir}/tesstractor
%{_bindir}/tesstractor-plot
%{_unitdir}/tesstractor.service
%{_unitdir}/tesstractor-plot.service
%{_unitdir}/tesstractor-plot.timer
%dir %{_sysconfdir}/tesstractor
%config(noreplace) %{_sysconfdir}/tesstractor/config.ini
%dir %{_sharedstatedir}/tesstractor


%changelog
* Tue Oct 27 2026 Sergio Pascual <sergiopr@fis.ucm.es> - 0.8.0-1
- Update to 0.8.0, built with pyproject macros
- Install the systemd units and the sample configuration

* Mon Mar 04 2019 Sergio Pascual <sergiopr at fedoraproject.com> - 0.5.1-1
- Initial SPEC
