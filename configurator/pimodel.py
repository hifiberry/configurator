import logging


# Which Pi versions can act as a USB peripheral, and on which physical port.
# None means the hardware has no usable device-mode port.
# Verified: Pi5 and CM5 expose an identical dwc2 node (usb@480000); Pi4/CM4
# expose the same controller at usb@7e980000. Only the dwc2 port can be a
# gadget -- USB-A ports are XHCI host-only.
USB_GADGET_SUPPORT = {
    "0W": "micro-USB",
    "02W": "micro-USB",
    "3A+": "micro-USB",
    "3B": "micro-USB",
    "3B+": "micro-USB",
    "4": "USB-C",
    "CM4": "micro-USB",
    "5": "USB-C",
    "CM5": "USB-C",
    "2": None,
    "unknown": None,
}


class PiModel:
    def __init__(self):
        self.model_name = "unknown"
        self.version = "unknown"
        self._detect()  # Automatically run detection when the object is initialized

    def _detect(self):
        """Detect the Raspberry Pi model by reading the device tree."""
        try:
            with open("/proc/device-tree/model", "r") as model_file:
                self.model_name = model_file.read().strip()
        except FileNotFoundError:
            logging.error("Device tree model file not found.")
            return

        logging.info(f"Detected model: {self.model_name}")
        self._set_model_details()

    def _set_model_details(self):
        """Set model details based on the detected model name."""
        if "3 Model B+" in self.model_name or "3 Model B Plus" in self.model_name:
            self.version = "3B+"
        elif "3 Model A Plus" in self.model_name:
            self.version = "3A+"
        elif "3 Model B" in self.model_name:
            self.version = "3B"
        elif "4 Model B" in self.model_name:
            self.version = "4"
        elif "Compute Module 4" in self.model_name:
            self.version = "CM4"
        elif "Pi Zero W" in self.model_name:
            self.version = "0W"
        elif "Pi Zero 2" in self.model_name:
            self.version = "02W"
        elif "Pi 2 Model" in self.model_name:
            self.version = "2"
        elif "Pi 5 Model" in self.model_name:
            self.version = "5"
        elif "Compute Module 5" in self.model_name:
            self.version = "CM5"
        else:
            logging.warning(f"Unknown Raspberry Pi model: {self.model_name}")
            self.version = "unknown"

        logging.info(f"Pi Version: {self.version}")

    def get_model_name(self):
        """Return the detected model name."""
        return self.model_name

    def get_version(self):
        """Return the detected Pi version."""
        return self.version

    def usb_gadget_port(self):
        """Return the port usable for USB device mode, or None if unsupported."""
        return USB_GADGET_SUPPORT.get(self.version)

    def supports_usb_gadget(self):
        """True if this model can act as a USB peripheral."""
        return self.usb_gadget_port() is not None


def main():
    """Main function to detect and print the Raspberry Pi model."""
    # Disable logging
    logging.getLogger().setLevel(logging.CRITICAL)
    
    pi_model = PiModel()  # Detection happens here automatically
    print(f"Model: {pi_model.get_model_name()}")
    print(f"Version: {pi_model.get_version()}")


if __name__ == "__main__":
    main()

