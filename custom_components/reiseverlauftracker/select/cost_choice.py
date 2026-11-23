"""Category and country of the travel costs form."""

from collections.abc import Mapping
from typing import Any

from custom_components.reiseverlauftracker.coordinator.cost_form import travel_cost_data
from custom_components.reiseverlauftracker.coordinator.logbook import CostCategory
from custom_components.reiseverlauftracker.entity import ReiseverlaufEntity
from homeassistant.components.select import SelectEntity


class ReiseverlaufCostCategory(SelectEntity, ReiseverlaufEntity):
    """Kind of the next travel cost: toll, vignette, ferry, tunnel, pitch or other."""

    _attr_options = [category.value for category in CostCategory]

    @property
    def current_option(self) -> str:
        """Return the chosen category."""
        return self.coordinator.cost_form.category.value

    async def async_select_option(self, option: str) -> None:
        """Choose the category."""
        self.coordinator.cost_form.set_category(option)


class ReiseverlaufCostCountry(SelectEntity, ReiseverlaufEntity):
    """Country of the next travel cost: the trip's countries first, then the toll countries, then none."""

    @property
    def options(self) -> list[str]:
        """Return the lower-case country codes and "none"."""
        return self.coordinator.cost_form.country_options()

    @property
    def current_option(self) -> str:
        """Return the chosen country."""
        return self.coordinator.cost_form.country_option

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the countries of the chosen trip, as found along its track."""
        trip = self.coordinator.cost_form.trip()
        return {"laender_der_reise": list(trip.countries or ()) if trip else []}

    async def async_select_option(self, option: str) -> None:
        """Choose the country."""
        self.coordinator.cost_form.set_country(option)


class ReiseverlaufCostEntry(SelectEntity, ReiseverlaufEntity):
    """Lists "new" and the stored costs of the chosen trip, newest first, to change or delete one."""

    @property
    def options(self) -> list[str]:
        """Return "new" and the cost labels."""
        return self.coordinator.cost_form.entry_options()

    @property
    def current_option(self) -> str:
        """Return the cost being edited, or "new"."""
        return self.coordinator.cost_form.entry_option()

    @property
    def extra_state_attributes(self) -> Mapping[str, Any]:
        """Return the stored values of the chosen cost, for the dashboard."""
        cost = self.coordinator.cost_form.edited()
        return {"eintrag": travel_cost_data(cost) if cost else None}

    async def async_select_option(self, option: str) -> None:
        """Fill the form with the chosen cost, or clear it for a new one."""
        self.coordinator.cost_form.select_entry(option)
