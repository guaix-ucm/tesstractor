# aiomqtt is not packaged in Fedora, it is built in the COPR
# project of tesstractor: copr.fedorainfracloud.org/coprs/sergiopr/tesstractor
Name:           python-aiomqtt
Version:        2.5.1
Release:        1%{?dist}
Summary:        The idiomatic asyncio MQTT client

License:        BSD-3-Clause
URL:            https://github.com/empicano/aiomqtt
Source:         %{pypi_source aiomqtt}

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-pytest

%global _description %{expand:
aiomqtt is an asyncio MQTT client, based on paho-mqtt.}

%description %_description

%package -n python3-aiomqtt
Summary:        %{summary}

%description -n python3-aiomqtt %_description


%prep
%autosetup -p1 -n aiomqtt-%{version}


%generate_buildrequires
%pyproject_buildrequires


%build
%pyproject_wheel


%install
%pyproject_install
%pyproject_save_files -l aiomqtt


%check
%pyproject_check_import
# test_client.py needs a MQTT broker on the network
%pytest tests/test_topic.py tests/test_exceptions.py


%files -n python3-aiomqtt -f %{pyproject_files}
%doc README.md CHANGELOG.md


%changelog
* Tue Oct 27 2026 Sergio Pascual <sergiopr@fis.ucm.es> - 2.5.1-1
- Initial package
