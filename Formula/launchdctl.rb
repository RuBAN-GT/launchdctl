class Launchdctl < Formula
  include Language::Python::Virtualenv

  desc "Launch Daemon Controller for macOS launchd"
  homepage "https://github.com/RuBAN-GT/launchdctl"
  url "https://github.com/RuBAN-GT/launchdctl/archive/refs/tags/v1.0.1.tar.gz"
  sha256 "8f78f7038f9c80d7cc2fe9403ff87989a29de3bb3e1e1ca37a959ded7c294c81"
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
