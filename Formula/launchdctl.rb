class Launchdctl < Formula
  include Language::Python::Virtualenv

  desc "Launch Daemon Controller for macOS launchd"
  homepage "https://github.com/RuBAN-GT/launchdctl"
  url "https://github.com/RuBAN-GT/launchdctl/archive/refs/tags/v1.0.0.tar.gz"
  sha256 "de7d935ab229ba124bc05c0fd38f00b6f0d707ed4355641a6d1a0f17a6a45394"
  license "MIT"
  head "https://github.com/RuBAN-GT/launchdctl.git", branch: "master"

  depends_on "yq"
  depends_on "python@3.13"

  def install
    venv = virtualenv_create(libexec, Formula["python@3.13"].opt_bin/"python3.13")
    venv.pip_install_and_link buildpath
    # std_pip_args uses --no-deps, so install rich (and its deps) separately.
    system libexec/"bin/python", "-m", "pip", "install", "rich"

    (share/"launchdctl").install "config.example.yaml"
  end

  def caveats
    <<~EOS
      Example config:
        #{share}/launchdctl/config.example.yaml

      Copy and edit:
        mkdir -p ~/.config/launchdctl
        cp #{share}/launchdctl/config.example.yaml ~/.config/launchdctl/config.yaml
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/launchdctl --version")
    assert_match "Launch Daemon Controller", shell_output("#{bin}/launchdctl --help")
    assert_path_exists share/"launchdctl/config.example.yaml"
  end
end
