

---
 ```python
 array([7.58741176, 8.11628778, 8.73371747, 8.8451669 , 7.8562491 ,
       7.33207755, 7.76590675, 7.38971382, 8.90593802, 9.30635235,
       9.30179745, 8.15763024, 9.14543335, 8.32226943, 9.57808109,
       8.83685752, 7.20371513, 8.82544692, 8.90576024, 9.31980052,
       9.70301679, 8.88379221, 9.50760904, 9.34993659, 8.92814066,
       8.98799509, 9.54499771, 9.84702654, 9.47065557, 9.22645057,
       7.93038566])
 /tmp/ipykernel_3465/4108593701.py:21: FutureWarning: In a future version of xarray the default value for data_vars will change from data_vars='all' to data_vars=None. This is likely to lead to different results when multiple datasets have matching variables with overlapping values. To opt in to new defaults and get rid of these warnings now use `set_options(use_new_combine_kwarg_defaults=True) or set data_vars explicitly.
   dset = xr.open_mfdataset(list(files), combine='by_coords')
```
---

