import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

from src.cmdline import CmdlineTxt


class TestCmdlineTxtInitialization:
    """Tests for CmdlineTxt initialization and file discovery."""

    def test_find_cmdline_file_in_firmware(self):
        """Test finding cmdline.txt in /boot/firmware."""
        with tempfile.TemporaryDirectory() as tmpdir:
            firmware_path = Path(tmpdir) / "firmware"
            firmware_path.mkdir()
            cmdline_file = firmware_path / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200\n")
            
            with patch("src.cmdline.os.path.exists") as mock_exists:
                def exists_side_effect(path):
                    if path == str(cmdline_file):
                        return True
                    return False
                
                mock_exists.side_effect = exists_side_effect
                
                with patch("builtins.open", create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = "console=serial0,115200"
                    
                    cmdline = CmdlineTxt.__new__(CmdlineTxt)
                    cmdline.file_path = str(cmdline_file)
                    cmdline.content = "console=serial0,115200"
                    cmdline.original_content = "console=serial0,115200"
                    
                    assert cmdline.file_path == str(cmdline_file)

    def test_init_reads_file_content(self):
        """Test that initialization reads file content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 ipv6.disable=1\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                
                assert cmdline.content == "console=serial0,115200 ipv6.disable=1"
                assert cmdline.original_content == "console=serial0,115200 ipv6.disable=1"

    def test_init_stores_original_content(self):
        """Test that original content is preserved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            original_content = "root=/dev/mmcblk0p2 rootfstype=ext4 rootwait"
            cmdline_file.write_text(original_content + "\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.content = "modified content"
                
                assert cmdline.original_content == original_content
                assert cmdline.content == "modified content"


class TestSerialConsole:
    """Tests for serial console enable/disable functionality."""

    def test_enable_serial_console_adds_token(self):
        """Test enabling serial console adds the token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2 rootfstype=ext4\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                
                assert "console=serial0,115200" in cmdline.content
                assert cmdline.content.startswith("console=serial0,115200")

    def test_enable_serial_console_already_enabled(self):
        """Test enabling serial console when already enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                original_content = cmdline.content
                cmdline.enable_serial_console()
                
                assert cmdline.content == original_content

    def test_disable_serial_console_removes_token(self):
        """Test disabling serial console removes the token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 root=/dev/mmcblk0p2 rootfstype=ext4\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.disable_serial_console()
                
                assert "console=serial0,115200" not in cmdline.content
                assert "root=/dev/mmcblk0p2" in cmdline.content

    def test_disable_serial_console_already_disabled(self):
        """Test disabling serial console when already disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2 rootfstype=ext4\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                original_content = cmdline.content
                cmdline.disable_serial_console()
                
                assert cmdline.content == original_content

    def test_enable_serial_console_inserts_at_beginning(self):
        """Test that serial console token is inserted at the beginning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2 rootfstype=ext4\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                
                tokens = cmdline.content.split()
                assert tokens[0] == "console=serial0,115200"


class TestIPv6:
    """Tests for IPv6 enable/disable functionality."""

    def test_enable_ipv6_removes_disable_token(self):
        """Test enabling IPv6 removes the disable token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 ipv6.disable=1 root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_ipv6()
                
                assert "ipv6.disable=1" not in cmdline.content
                assert "console=serial0,115200" in cmdline.content
                assert "root=/dev/mmcblk0p2" in cmdline.content

    def test_enable_ipv6_already_enabled(self):
        """Test enabling IPv6 when already enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                original_content = cmdline.content
                cmdline.enable_ipv6()
                
                assert cmdline.content == original_content

    def test_disable_ipv6_adds_disable_token(self):
        """Test disabling IPv6 adds the disable token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 root=/dev/mmcblk0p2 rootfstype=ext4\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.disable_ipv6()
                
                assert "ipv6.disable=1" in cmdline.content

    def test_disable_ipv6_already_disabled(self):
        """Test disabling IPv6 when already disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 ipv6.disable=1 root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                original_content = cmdline.content
                cmdline.disable_ipv6()
                
                assert cmdline.content == original_content

    def test_disable_ipv6_appends_token(self):
        """Test that IPv6 disable token is appended to the end."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.disable_ipv6()
                
                tokens = cmdline.content.split()
                assert tokens[-1] == "ipv6.disable=1"


class TestFileOperations:
    """Tests for file read/write and backup operations."""

    def test_read_file_strips_whitespace(self):
        """Test that file reading strips leading/trailing whitespace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("  console=serial0,115200  \n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                
                assert cmdline.content == "console=serial0,115200"

    def test_save_creates_backup(self):
        """Test that save() creates a backup file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                cmdline.save()
                
                backup_file = Path(str(cmdline_file) + ".backup")
                assert backup_file.exists()
                assert backup_file.read_text() == "root=/dev/mmcblk0p2\n"

    def test_save_writes_content_with_newline(self):
        """Test that save() writes content with trailing newline."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                cmdline.save()
                
                content = cmdline_file.read_text()
                assert content.endswith("\n")
                assert content == "console=serial0,115200 root=/dev/mmcblk0p2\n"

    def test_save_no_changes_no_backup(self):
        """Test that save() doesn't create backup when no changes made."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            original_content = "root=/dev/mmcblk0p2"
            cmdline_file.write_text(original_content + "\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.save()
                
                backup_file = Path(str(cmdline_file) + ".backup")
                assert not backup_file.exists()

    def test_save_only_when_content_changes(self):
        """Test that save() only writes when content actually changes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            original = "root=/dev/mmcblk0p2"
            cmdline_file.write_text(original + "\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                
                # Save without changes - should not create backup
                cmdline.save()
                assert not (Path(str(cmdline_file) + ".backup").exists())
                
                # Now make a change
                cmdline.enable_serial_console()
                assert cmdline.content != cmdline.original_content
                
                # Save with changes - should create backup
                cmdline.save()
                assert (Path(str(cmdline_file) + ".backup").exists())

    def test_create_backup_overwrites_existing(self):
        """Test that backup is overwritten on subsequent saves."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                # First modification
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                cmdline.save()
                
                # Second modification
                cmdline = CmdlineTxt()
                cmdline.disable_serial_console()
                cmdline.enable_ipv6()
                cmdline.save()
                
                backup_file = Path(str(cmdline_file) + ".backup")
                backup_content = backup_file.read_text()
                
                # Backup should contain the first save (serial console enabled)
                assert "console=serial0,115200" in backup_content


class TestTokenHandling:
    """Tests for proper token manipulation."""

    def test_multiple_tokens_preserved(self):
        """Test that other tokens are preserved when modifying content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            original = "root=/dev/mmcblk0p2 rootfstype=ext4 rootwait elevator=noop"
            cmdline_file.write_text(original + "\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                
                tokens = cmdline.content.split()
                assert "root=/dev/mmcblk0p2" in tokens
                assert "rootfstype=ext4" in tokens
                assert "rootwait" in tokens
                assert "elevator=noop" in tokens
                assert "console=serial0,115200" in tokens

    def test_combined_modifications(self):
        """Test enabling/disabling multiple features together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                cmdline.disable_ipv6()
                cmdline.save()
                
                tokens = cmdline.content.split()
                assert "console=serial0,115200" in tokens
                assert "ipv6.disable=1" in tokens
                assert "root=/dev/mmcblk0p2" in tokens

    def test_duplicate_tokens_handled(self):
        """Test that duplicate tokens are not created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                
                # Try enabling multiple times
                for _ in range(3):
                    cmdline.enable_serial_console()
                
                token_count = cmdline.content.count("console=serial0,115200")
                assert token_count == 1


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_cmdline_file(self):
        """Test handling of empty cmdline file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                
                assert "console=serial0,115200" in cmdline.content

    def test_single_token_file(self):
        """Test file with single token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                
                tokens = cmdline.content.split()
                assert len(tokens) == 2
                assert tokens[0] == "console=serial0,115200"
                assert tokens[1] == "root=/dev/mmcblk0p2"

    def test_remove_from_single_token_file(self):
        """Test removing token from file with only one token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.disable_serial_console()
                
                assert cmdline.content == ""

    def test_whitespace_normalization(self):
        """Test that multiple spaces are normalized to single space."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2  rootfstype=ext4   rootwait\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                cmdline = CmdlineTxt()
                cmdline.enable_serial_console()
                
                # Check no double spaces
                assert "  " not in cmdline.content


class TestMainFunction:
    """Tests for main() CLI function."""

    def test_main_enable_serial_console(self):
        """Test main() with --enable-serial-console flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                with patch("sys.argv", ["cmdline", "--enable-serial-console"]):
                    from src.cmdline import main
                    main()
                
                content = cmdline_file.read_text()
                assert "console=serial0,115200" in content

    def test_main_disable_serial_console(self):
        """Test main() with --disable-serial-console flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("console=serial0,115200 root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                with patch("sys.argv", ["cmdline", "--disable-serial-console"]):
                    from src.cmdline import main
                    main()
                
                content = cmdline_file.read_text()
                assert "console=serial0,115200" not in content

    def test_main_enable_ipv6(self):
        """Test main() with --enable-ipv6 flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("ipv6.disable=1 root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                with patch("sys.argv", ["cmdline", "--enable-ipv6"]):
                    from src.cmdline import main
                    main()
                
                content = cmdline_file.read_text()
                assert "ipv6.disable=1" not in content

    def test_main_disable_ipv6(self):
        """Test main() with --disable-ipv6 flag."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cmdline_file = Path(tmpdir) / "cmdline.txt"
            cmdline_file.write_text("root=/dev/mmcblk0p2\n")
            
            with patch.object(CmdlineTxt, "_find_cmdline_file", return_value=str(cmdline_file)):
                with patch("sys.argv", ["cmdline", "--disable-ipv6"]):
                    from src.cmdline import main
                    main()
                
                content = cmdline_file.read_text()
                assert "ipv6.disable=1" in content

    def test_main_requires_argument(self):
        """Test main() requires a command-line argument."""
        with patch("sys.argv", ["cmdline"]):
            from src.cmdline import main
            
            with pytest.raises(SystemExit):
                main()
