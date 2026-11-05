# typed: false
# frozen_string_literal: true

class Vim2bat < Formula
  include Language::Python::Virtualenv

  desc "Generate bat themes from Vim colorschemes"
  homepage "https://github.com/redodson01/vim2bat"
  url "https://github.com/redodson01/vim2bat/archive/refs/tags/vVERSION_PLACEHOLDER.tar.gz"
  sha256 "SHA_PLACEHOLDER"
  license "MIT"

  depends_on "bat"
  depends_on "python@3.15"
  uses_from_macos "vim"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/vim2bat --version")

    ENV["BAT_CONFIG_DIR"] = testpath/"bat"
    ENV["BAT_CACHE_PATH"] = testpath/"bat-cache"
    ENV["XDG_CACHE_HOME"] = testpath/"cache"
    system bin/"vim2bat", "desert"
    assert_path_exists testpath/"bat/themes/vim-desert.tmTheme"
  end
end
