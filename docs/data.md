# Данные и схема HEC-DB

Одна строка соответствует одному численному свойству одного образца в конкретных условиях. Материал с разным способом приготовления или формой образца получает разные идентификаторы. Общее число **31 запись образца** включает 11 high-entropy oxides, 15 medium-entropy oxides и 5 low-entropy benchmarks. Всего внесено **106 экспериментальных наблюдений**. Все значения из статей: свойства, рассчитанные авторами на основе экспериментальных входных данных, помечены experimental, а детали формулы или поправки сохранены в полях method и basis. Численные тестовые значения существуют только в синтетических фикстурах Pytest.

## Поля обмена

| Поля | Содержание |
| --- | --- |
| material_id, composition, family, material_class | Идентификатор образца с учётом регистра, формула, семейство и класс. Рекомендуется добавить префикс группы или исследования |
| crystal_structure, constituents | Структура и пропорции элементов, включая доли на подрешётках, когда их приводит источник |
| synthesis_method, processing_conditions, specimen_form | Получение, обработка и фактическая форма образца, например sintered bulk или coating |
| applications | Одна или несколько полных меток применения через точку с запятой |
| property, value, unit | Свойство из реестра, исходное число из источника и исходная единица. Значение может быть пустым |
| uncertainty, uncertainty_type | Неотрицательная половина указанного интервала ± в единицах unit и его тип. При неизвестном типе сохраните исходное обозначение |
| temperature_c, temperature_start_c, frequency_hz, pressure_kpa | Точка измерения или конец интервала, начало интервала, частота и давление. Введите °C, Hz и kPa соответственно |
| method, basis, measurement_conditions, cohort | Метод, определение/поправка, дополнительные условия и метка сопоставимой серии. Например, thermal conductivity до и после porosity correction имеет разный basis |
| replicate_id | Метка отдельно опубликованного повторного результата при совпадающих условиях |
| data_type, publication_title, doi, source_url, source_locator | Происхождение (experimental, computational, synthetic), название первоисточника, DOI или URL и точное место значения в источнике |

Обязательны столбцы material_id, composition, family, material_class, applications, property, value, unit, data_type, publication_title и source_locator. Для реальных данных заполните doi и/или source_url. Для чисел используйте десятичную точку. В числовых полях пустая ячейка и обозначения NA, N/A, NaN, #N/A, ND, N.D. и тире означают пропуск. Пометка NA в текстовом идентификаторе допустима. Для отбора нужны specimen_form, method, basis и cohort. Для набора из одной работы сохраняйте формулировку «температура не указана» пустой числовой ячейкой. Укажите отступления от типичного режима в measurement_conditions. Не выносите данные из таблицы обзора, если она ссылается на доступный первоисточник.

При одинаковом ID, свойстве, происхождении, условиях, источнике и метке повторения валидатор сверяет результат в канонических единицах. Повтор с согласующимся числом и неопределённостью записывается в журнал и сворачивается, а отличающиеся значения требуют проверки. Если результат с таким ключом одновременно пустой и заполненный, сохраняется заполненный. Конвертация чисел нужна программе для расчёта. Экспорт валидированного набора сохраняет value и unit в исходных единицах. Программа проверяет формат DOI и URL. Связь числа с конкретным источником подтверждается вручную по source_locator.

### Канонические единицы

| Свойство | Идентификатор | Единица |
| --- | --- | --- |
| Thermal conductivity | thermal_conductivity | W/(m*K) |
| Thermal expansion coefficient | thermal_expansion | 1e-6/K |
| Melting, glass transition, crystallization temperature | melting_temperature, glass_transition_temperature, crystallization_temperature | degC |
| Density, relative density | density, relative_density | g/cm3, % |
| Hardness, Young’s modulus | hardness, youngs_modulus | GPa |
| Fracture toughness | fracture_toughness | MPa*m^0.5 |
| Dielectric constant and loss, refractive index | dielectric_constant, dielectric_loss, refractive_index | 1 |
| Breakdown strength | breakdown_strength | kV/mm |
| Energy storage density | energy_storage_density | J/cm3 |
| Efficiency | efficiency | % |
| Electrical conductivity | electrical_conductivity | S/m |

Список допустимых входных единиц указан в [реестре](../hec_screen/schema.py). Например, 1580 mW/(m*K) преобразуются в 1.58 W/(m*K), 11 ppm/K — в 11 × 10⁻⁶ K⁻¹, температура плавления в Kelvins — в degC вычитанием 273.15. Ширину неопределённости умножают на модуль коэффициента без температурного сдвига. Новое свойство добавляйте с явными единицами и правилами проверки. Учебный шаблон задаёт группы полей. Заголовки конкретной таблицы другой группы нужно согласовать или сопоставить явно через mapping.

## Первичные источники чисел

| Работа | Записи образцов | Наблюдения | Место извлечения |
| --- | ---: | ---: | --- |
| [Huang et al., Coatings (2026)](https://www.mdpi.com/2079-6412/16/1/79) | 3 | 17 | Tables 1–2, §§2–4. Взяты только результаты авторов с пометкой This work |
| [Wright et al., Scripta Materialia (2020)](https://doi.org/10.1016/j.scriptamat.2020.02.011) | 22 | 66 | Table 1 и описание методов в [рукописи авторов](https://arxiv.org/pdf/1912.11734#page=12). Три высокоэнтропийных состава, 15 среднеэнтропийных и четыре низкоэнтропийных эталона по критерию из статьи. Температура в таблице не дана |
| [Liu et al., Journal of Advanced Ceramics (2024)](https://file.sciopen.com/sciopen_public/1799618754483167233.pdf) | 5 | 17 | Table 2 и §§2–3. Четыре высокоэнтропийных образца и контроль GZ |
| [Anandkumar et al., Nanomaterials (2026)](https://www.mdpi.com/2079-4991/16/22/1503) | 1 | 6 | §§2–3, Table 2 и Figure 7c с числами в тексте. Effective thermal conductivity относится к пористому образцу и хранится отдельно от intrinsic conductivity |

## Дополнительные первичные публикации для расширения

Вместе с четырьмя работами выше список включает 20 первичных публикаций. Далее приведены проверенные библиографические записи. Из этих 16 работ значения ещё не перенесены в CSV/XLSX. Перед переносом проверьте конкретные образцы, режимы испытаний и определения свойств в тексте и приложениях.

| Направление поиска | Публикация |
| --- | --- |
| Синтез пирохлоров, thermal conductivity | [High-entropy pyrochlores with low thermal conductivity for thermal barrier coating materials](https://link.springer.com/article/10.1007/s40145-019-0342-4) |
| Фторитовые цирконаты, thermal expansion и механика | [High-entropy rare-earth zirconate ceramics with low thermal conductivity for advanced thermal-barrier coatings](https://link.springer.com/article/10.1007/s40145-022-0589-z) |
| Цирконаты с регулируемыми свойствами | [Designing high-entropy rare-earth zirconates with tunable thermophysical properties for thermal barrier coatings](https://www.sciencedirect.com/science/article/pii/S092583882203105X) |
| Двойные фазы, зависимость thermal conductivity от фазового состава | [Dual-phase rare-earth-zirconate high-entropy ceramics with glass-like thermal conductivity](https://www.sciencedirect.com/science/article/pii/S0955221920309468) |
| Одновременная оценка thermal expansion и механики | [Multicomponent high-entropy zirconates with comprehensive properties for advanced thermal barrier coating](https://www.sciencedirect.com/science/article/abs/pii/S1359646219307250) |
| Изменение фаз с составом в многокомпонентных оксидах | [Single-phase duodenary high-entropy fluorite/pyrochlore oxides with an order-disorder transition](https://www.sciencedirect.com/science/article/pii/S135964542100238X) |
| Сравнение medium и high entropy в двухфазных цирконатах | [Thermophysical and mechanical properties of dual-phase medium- and high-entropy rare-earth zirconate ceramics](https://www.sciencedirect.com/science/article/pii/S0272884223027554) |
| Покрытия, полученные atmospheric plasma spraying | [Preparation and Thermophysical Properties of New Multi-Component Entropy-Stabilized Oxide Ceramics for Thermal Barrier Coatings](https://www.mdpi.com/2079-6412/13/5/937) |
| Перспективные cerates | [High-entropy rare-earth cerate as a potential thermal barrier material](https://link.springer.com/article/10.1007/s40145-021-0563-1) |
| Cerates с разным числом компонентов | [Elevating the comprehensive thermal properties of rare-earth cerates through high-entropy design](https://www.sciopen.com/article/10.1016/j.jmat.2023.12.004?issn=2352-8478) |
| Niobates и tantalates для расширения семейств | [High entropy defective fluorite structured rare-earth niobates and tantalates for thermal barrier applications](https://www.sciopen.com/article/10.1007/s40145-020-0368-7) |
| Двухфазная система zirconate/tantalate | [Dual-phase zirconate/tantalate high-entropy ceramics boost thermal properties and fracture toughness for thermal barrier coating materials](https://www.sciencedirect.com/science/article/pii/S223878542401977X) |
| Сравнение цирконатов с Tb, Er, Yb и Lu | [Preparation, thermophysical properties, and mechanical properties of high-entropy zirconate ceramics](https://doi.org/10.1007/s43207-026-00600-x) |
| Ce–Sc легирование и измерения при 1500 °C | [Synergistic optimization of thermal and mechanical properties in Ce–Sc Co-doped high-entropy fluorite zirconates](https://www.sciencedirect.com/science/article/pii/S0272884226007571) |
| Thermal cycling у нанесённого покрытия | [Mechanical and thermophysical properties of the solution precursor plasma sprayed high-entropy ceramic coating and its thermal cycling behavior](https://www.sciencedirect.com/science/article/pii/S0272884226037715) |
| Влияние нестехиометрии цирконатов | [Enhanced Thermophysical Properties in Rare-Earth Zirconate High-Entropy Ceramics via Non-Stoichiometric Design](https://onlinelibrary.wiley.com/doi/full/10.1111/jace.71213) |
