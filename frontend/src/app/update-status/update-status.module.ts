import { NgModule } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule, Routes } from '@angular/router';
import { UpdateStatusComponent } from './update-status.component';

const routes: Routes = [
  { path: '', component: UpdateStatusComponent }
];

@NgModule({
  declarations: [UpdateStatusComponent],
  imports: [
    CommonModule,
    FormsModule,
    RouterModule.forChild(routes),
  ]
})
export class UpdateStatusModule {}
