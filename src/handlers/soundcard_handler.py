#!/usr/bin/env python3
"""
Soundcard Handler for HiFiBerry Configuration API

Provides API endpoints for managing sound card configurations.
"""

import logging
from typing import Dict, List, Any, Optional, Union, cast, TYPE_CHECKING
from flask import request, jsonify
from ..soundcard import SOUND_CARD_DEFINITIONS  # type: ignore[import-untyped]
from ..soundcard_detector import SoundcardDetector  # type: ignore[import-untyped]
from ..soundcard import Soundcard  # type: ignore[import-untyped]
from ..configtxt import ConfigTxt
from ..configdb import ConfigDB

if TYPE_CHECKING:
    from flask import Response

logger = logging.getLogger(__name__)


class SoundcardHandler:
    """Handler for soundcard-related API operations"""

    def __init__(self):
        """Initialize the soundcard handler"""

    def handle_list_soundcards(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle GET /api/v1/soundcards - List all available sound cards

        Returns:
            JSON response with list of sound cards and their properties
        """
        try:
            soundcards_list: List[Dict[str, Any]] = []

            for card_name, attributes in SOUND_CARD_DEFINITIONS.items():  # type: ignore[union-attr]
                soundcard_info: Dict[str, Any] = {
                    "name": card_name,
                    "dtoverlay": attributes.get("dtoverlay", "unknown"),  # type: ignore[misc]
                    "volume_control": attributes.get("volume_control"),  # type: ignore[misc]
                    "headphone_volume_control": (  # type: ignore[misc]
                        attributes.get("headphone_volume_control")
                    ),
                    "output_channels": attributes.get("output_channels", 0),  # type: ignore[misc]
                    "input_channels": attributes.get("input_channels", 0),  # type: ignore[misc]
                    "features": attributes.get("features", []),  # type: ignore[misc]
                    "supports_dsp": attributes.get("supports_dsp", False),  # type: ignore[misc]
                    "card_type": attributes.get("card_type", []),  # type: ignore[misc]
                    "is_pro": attributes.get("is_pro", False)  # type: ignore[misc]
                }
                soundcards_list.append(soundcard_info)

            return jsonify({
                "status": "success",
                "data": {
                    "soundcards": soundcards_list,
                    "count": len(soundcards_list)
                }
            })  # type: ignore[return-value]

        except OSError as e:
            logger.error("Error listing soundcards: %s", e)
            return jsonify({
                "status": "error",
                "message": "Failed to list soundcards",
                "error": str(e)
            }), 500  # type: ignore[return-value]

    def handle_set_dtoverlay(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/soundcard/dtoverlay - Set device tree overlay in config.txt

        Expected JSON payload:
        {
            "dtoverlay": "hifiberry-dac",
            "remove_existing": true  # optional, defaults to true
        }

        Returns:
            JSON response with success/error status
        """
        try:
            # Parse JSON request
            data: Dict[str, Any] = cast(Dict[str, Any], request.get_json() or {})
            if not data:
                return jsonify({
                    "status": "error",
                    "message": "No JSON data provided"
                }), 400  # type: ignore[return-value]

            dtoverlay: Optional[str] = data.get('dtoverlay')
            if not dtoverlay:
                return jsonify({
                    "status": "error",
                    "message": "dtoverlay parameter is required"
                }), 400  # type: ignore[return-value]

            remove_existing: bool = data.get('remove_existing', True)

            # Validate that the dtoverlay exists in our sound card definitions
            valid_overlays: List[Any] = [
                attrs.get('dtoverlay')
                for attrs in SOUND_CARD_DEFINITIONS.values()  # type: ignore[misc]
            ]
            if dtoverlay not in valid_overlays:
                return jsonify({
                    "status": "error",
                    "message": (
                        "Invalid dtoverlay '%s'. Must be one of the supported HiFiBerry overlays."  # pylint: disable=consider-using-f-string
                        % dtoverlay
                    ),
                    "valid_overlays": sorted(
                        list(set(v for v in valid_overlays if v is not None))
                    )
                }), 400  # type: ignore[return-value]

            # Initialize ConfigTxt handler
            config = ConfigTxt()

            # Remove existing HiFiBerry overlays if requested
            if remove_existing:
                config.remove_hifiberry_overlays()

            # Add the new overlay
            config.enable_overlay(dtoverlay)

            # Save changes
            config.save()

            # Build response message
            # pylint: disable=consider-using-f-string
            if config.changes_made:
                message = "Successfully set dtoverlay to '%s'" % dtoverlay
                if remove_existing:
                    message += " (removed existing HiFiBerry overlays)"
            else:
                message = "dtoverlay '%s' was already configured" % dtoverlay
            # pylint: enable=consider-using-f-string

            return jsonify({
                "status": "success",
                "message": message,
                "data": {
                    "dtoverlay": dtoverlay,
                    "changes_made": config.changes_made,
                    "reboot_required": config.changes_made
                }
            })  # type: ignore[return-value]

        except FileNotFoundError as e:
            logger.error("Config file not found: %s", e)
            return jsonify({
                "status": "error",
                "message": "Config file not found",
                "error": str(e)
            }), 404  # type: ignore[return-value]

        except (OSError, AttributeError, ValueError) as e:
            logger.error("Error setting dtoverlay: %s", e)
            return jsonify({
                "status": "error",
                "message": "Failed to set dtoverlay",
                "error": str(e)
            }), 500  # type: ignore[return-value]

    def handle_detection_status(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle GET /api/v1/soundcard/detection - Get detection status

        Returns:
            JSON response with detection enabled/disabled status and configured card
        """
        try:
            config = ConfigTxt()
            is_disabled = config.is_detection_disabled()

            # Try to get the configured card name from config.txt comment
            configured_card_name = None
            configured_dtoverlay = None

            if is_disabled:
                # Pass the config file path to the detector
                detector = SoundcardDetector(config_file=config.file_path)
                configured_card_name = detector.detect_from_config_txt_comment()

                # Also try to get the dtoverlay value
                for line in config.lines:
                    stripped = line.strip()
                    if stripped.startswith("dtoverlay=hifiberry"):
                        configured_dtoverlay = stripped.split("=")[1].strip()
                        break

            return jsonify({
                "status": "success",
                "data": {
                    "detection_enabled": not is_disabled,
                    "detection_disabled": is_disabled,
                    "configured_card_name": configured_card_name,
                    "configured_dtoverlay": configured_dtoverlay
                }
            })  # type: ignore[return-value]

        except OSError as e:
            logger.error("Error checking detection status: %s", e)
            return jsonify({
                "status": "error",
                "message": "Failed to check detection status",
                "error": str(e)
            }), 500  # type: ignore[return-value]

    def handle_enable_detection(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/soundcard/detection/enable - Enable sound card detection

        This will also remove any HiFiBerry overlays from config.txt to allow auto-detection

        Returns:
            JSON response with success/error status
        """
        try:
            config = ConfigTxt()
            was_disabled = config.is_detection_disabled()

            # Remove HiFiBerry overlays to enable auto-detection
            config.remove_hifiberry_overlays()

            # Enable detection
            config.enable_detection()
            config.save()

            # Clear any pinned card from ConfigDB so SoundcardDetector's Step 0
            # no longer short-circuits to a stale value.
            try:
                ConfigDB().delete("soundcard.name")
            except (OSError, AttributeError) as e:
                logger.warning("Failed to clear soundcard.name from ConfigDB: %s", e)

            if was_disabled or config.changes_made:
                return jsonify({
                    "status": "success",
                    "message": "Sound card detection enabled and fixed overlays removed",
                    "data": {
                        "detection_enabled": True,
                        "changes_made": config.changes_made,
                        "reboot_required": True
                    }
                })  # type: ignore[return-value]

            return jsonify({
                "status": "success",
                "message": "Sound card detection was already enabled",
                "data": {
                    "detection_enabled": True,
                    "changes_made": False,
                    "reboot_required": False
                }
            })  # type: ignore[return-value]

        except (OSError, AttributeError) as e:
            logger.error("Error enabling detection: %s", e)
            return jsonify({
                "status": "error",
                "message": "Failed to enable sound card detection",
                "error": str(e)
            }), 500  # type: ignore[return-value]

    def handle_disable_detection(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle POST /api/v1/soundcard/detection/disable - Disable sound card detection

        Expected JSON payload (optional):
        {
            "card_name": "Beocreate 4-Channel Amplifier"  # Sets fixed sound card by name
        }

        If card_name is provided, sets the appropriate dtoverlay and disables detection.
        If card_name is not provided, only disables detection (keeps existing overlay).

        Returns:
            JSON response with success/error status
        """
        try:
            config = ConfigTxt()
            was_enabled = not config.is_detection_disabled()

            # Check if a card name was provided in the request
            data: Dict[str, Any] = (
                cast(Dict[str, Any], request.get_json() or {}) if request.is_json else {}
            )
            card_name: Optional[str] = data.get('card_name') if data else None

            if card_name:
                # Look up the card definition to get the dtoverlay
                card_def = SOUND_CARD_DEFINITIONS.get(card_name)  # type: ignore[union-attr]
                if not card_def:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Unknown sound card: '%s'" % card_name  # pylint: disable=consider-using-f-string
                        ),
                        "available_cards": list(
                            SOUND_CARD_DEFINITIONS.keys()
                        )  # type: ignore[arg-type]
                    }), 400

                dtoverlay = card_def.get('dtoverlay')  # type: ignore[union-attr]
                if not dtoverlay:
                    return jsonify({
                        "status": "error",
                        "message": (
                            "Sound card '%s' does not have a dtoverlay defined"  # pylint: disable=consider-using-f-string
                            % card_name
                        ),
                    }), 400

                # Remove existing HiFiBerry overlays and set the new one
                config.remove_hifiberry_overlays()
                config.disable_detection()
                config.enable_overlay(
                    dtoverlay,
                    card_name=card_name,
                    disable_eeprom=True
                )  # type: ignore[arg-type]
                config.save()

                # Persist the pinned card name so SoundcardDetector's Step 0 override
                # returns it (and config-soundcard reports the right volume_control etc.).
                try:
                    ConfigDB().set("soundcard.name", card_name)
                except (OSError, AttributeError) as e:
                    logger.warning("Failed to write soundcard.name to ConfigDB: %s", e)

                return jsonify({
                    "status": "success",
                    "message": (
                        "Fixed sound card set to '%s' with overlay '%s'" %  # pylint: disable=consider-using-f-string
                        (card_name, dtoverlay)
                    ),
                    "data": {
                        "card_name": card_name,
                        "dtoverlay": dtoverlay,
                        "detection_enabled": False,
                        "changes_made": config.changes_made,
                        "reboot_required": True
                    }
                })  # type: ignore[return-value]

            # No card name provided, just disable detection
            config.disable_detection()
            config.save()

            if was_enabled:
                return jsonify({
                    "status": "success",
                    "message": "Sound card detection disabled",
                    "data": {
                        "detection_enabled": False,
                        "changes_made": config.changes_made
                    }
                })  # type: ignore[return-value]

            return jsonify({
                "status": "success",
                "message": "Sound card detection was already disabled",
                "data": {
                    "detection_enabled": False,
                    "changes_made": False
                }
            })  # type: ignore[return-value]

        except (OSError, AttributeError) as e:
            logger.error("Error disabling detection: %s", e)
            return jsonify({
                "status": "error",
                "message": "Failed to disable sound card detection",
                "error": str(e)
            }), 500  # type: ignore[return-value]

    def handle_detect_live_soundcard(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle GET /api/v1/soundcard/detect-live - Run a fresh hardware
        detection pass, ignoring any pin written to ConfigDB or the
        config.txt `# HiFiBerry card:` comment. DSP-checksum refinement
        is still applied. Used by the setup wizard so it shows what is
        actually plugged in, not a stale pin from a previous run.

        Returns:
            JSON response with the freshly detected card and overlay.
        """
        try:
            detector = SoundcardDetector()
            detector.detect_card(ignore_pin=True)

            card_name: Optional[str] = detector.detected_card  # type: ignore[assignment]
            overlay: Optional[str] = detector.detected_overlay  # type: ignore[assignment]

            card_def: Optional[Dict[str, Any]] = (
                SOUND_CARD_DEFINITIONS.get(card_name) if card_name else None
            )  # type: ignore[arg-type,assignment]
            dtoverlay: Optional[str] = card_def.get("dtoverlay") if card_def else None

            return jsonify({
                "status": "success",
                "data": {
                    "card_name": card_name,
                    "overlay": overlay,
                    "dtoverlay": dtoverlay,
                    "card_detected": bool(card_name),  # type: ignore[arg-type]
                    "definition_found": card_def is not None,
                }
            })  # type: ignore[return-value]
        except (OSError, AttributeError) as e:
            logger.error("Error running live soundcard detection: %s", e)
            return jsonify({
                "status": "error",
                "message": "Failed to run live sound card detection",
                "error": str(e),
            }), 500  # type: ignore[return-value]

    def handle_detect_soundcard(self) -> 'Union[Response, tuple[Response, int]]':
        """
        Handle GET /api/v1/soundcard/detect - Detect current sound card

        Returns:
            JSON response with detected sound card name and dtoverlay
        """
        try:
            soundcard = Soundcard()

            if soundcard.name:  # type: ignore[union-attr]
                # Get the sound card definition
                card_def: Optional[Dict[str, Any]] = (
                    SOUND_CARD_DEFINITIONS.get(soundcard.name)
                )  # type: ignore[arg-type,assignment]
                dtoverlay: Optional[str] = card_def.get("dtoverlay") if card_def else "unknown"

                return jsonify({
                    "status": "success",
                    "message": "Sound card detected successfully",
                    "data": {
                        "card_name": soundcard.name,  # type: ignore[union-attr]
                        "dtoverlay": dtoverlay,
                        "volume_control": soundcard.volume_control,  # type: ignore[union-attr]
                        "headphone_volume_control": (  # type: ignore[union-attr]
                            soundcard.headphone_volume_control
                        ),
                        "hardware_index": soundcard.get_hardware_index(),
                        "output_channels": soundcard.output_channels,  # type: ignore[union-attr]
                        "input_channels": soundcard.input_channels,  # type: ignore[union-attr]
                        "features": soundcard.features,  # type: ignore[union-attr]
                        "hat_name": soundcard.hat_name,  # type: ignore[union-attr]
                        "supports_dsp": soundcard.supports_dsp,  # type: ignore[union-attr]
                        "card_type": soundcard.card_type,  # type: ignore[union-attr]
                        "card_detected": True,
                        "definition_found": card_def is not None
                    }
                })  # type: ignore[return-value]

            return jsonify({
                "status": "success",
                "message": "No sound card detected",
                "data": {
                    "card_name": None,
                    "dtoverlay": None,
                    "card_detected": False,
                    "definition_found": False
                }
            })  # type: ignore[return-value]

        except (OSError, AttributeError) as e:
            logger.error("Error detecting soundcard: %s", e)
            return jsonify({
                "status": "error",
                "message": "Failed to detect sound card",
                "error": str(e)
            }), 500
